#!/usr/bin/env python3
"""Publish built extension APKs as a Mihon extension repository (repo index v2).

Layout written to the repo branch:

    apk/<extension>.apk
    icon/<package>.png
    index.pb          # gzipped protobuf index (repo v2, used by Mihon 0.20+)
    index.json        # protobuf JSON form of the same index
    index.min.json    # legacy repo v1 index (kept for older apps)
    repo.json         # points apps at index.pb
    index.html        # plain download listing

Environment:
    GITHUB_REPOSITORY            owner/name, e.g. crixsz/tachiyomi-extensions-reborn
    APK_DIR                      directory containing the release APKs (default: <root>/apk)
    OUTPUT_JSON                  inspector output from the build job (default: <root>/output.json)
    REPO_DIR                     checked out repo branch (default: <root>/repo-out)
    REPO_BRANCH                  branch the files are served from (default: repo)
    SIGNING_KEY_FINGERPRINT      SHA-256 of the signing certificate
    CI_MODULES                   comma separated lang/name modules, used for language mapping
    REPO_DISPLAY_NAME            name shown in the app
"""

import gzip
import html
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import index_pb2
from google.protobuf import json_format

ROOT = Path(__file__).resolve().parents[2]
APK_DIR = Path(os.environ.get("APK_DIR", ROOT / "apk")).resolve()
REPO_DIR = Path(os.environ.get("REPO_DIR", ROOT / "repo-out")).resolve()
OUTPUT_JSON = Path(os.environ.get("OUTPUT_JSON", ROOT / "output.json")).resolve()
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "crixsz/tachiyomi-extensions-reborn")
REPO_BRANCH = os.environ.get("REPO_BRANCH", "repo")
REPO_DISPLAY_NAME = os.environ.get("REPO_DISPLAY_NAME", "Reborn Extensions")
REPO_WEBSITE = os.environ.get("REPO_WEBSITE", f"https://github.com/{GITHUB_REPOSITORY}")
SIGNING_KEY = os.environ.get(
    "SIGNING_KEY_FINGERPRINT",
    "ec5f36ddbeae4fde1c5c9c1484b1c9dfd9ca467f9dfe8cc2c0e2bd658f859656",
).replace(":", "").lower()
MODULES = [m.strip() for m in os.environ.get("CI_MODULES", "").split(",") if m.strip()]

RAW_BASE = f"https://github.com/{GITHUB_REPOSITORY}/raw/{REPO_BRANCH}"


def find_aapt() -> Path:
    roots = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")]
    exe_name = "aapt.exe" if os.name == "nt" else "aapt"
    for root in filter(None, roots):
        build_tools = Path(root) / "build-tools"
        if not build_tools.is_dir():
            continue
        versions = [p for p in build_tools.iterdir() if p.is_dir()]
        versions.sort(key=lambda p: [int(x) for x in re.findall(r"\d+", p.name)])
        for version in reversed(versions):
            exe = version / exe_name
            if exe.exists():
                return exe
    raise SystemExit("aapt not found: set ANDROID_HOME or ANDROID_SDK_ROOT")


def badging(aapt: Path, apk: Path) -> str:
    return subprocess.run(
        [str(aapt), "dump", "--include-meta-data", "badging", str(apk)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def grab(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else default


def language_for(package_name: str) -> str:
    for module in MODULES:
        parts = module.split("/")
        if len(parts) != 2:
            continue
        lang, name = parts
        if package_name.endswith(f".{lang}.{name}"):
            return lang
    return ""


def load_sources() -> dict:
    if not OUTPUT_JSON.is_file():
        print(f"warning: {OUTPUT_JSON} not found, publishing without source metadata", file=sys.stderr)
        return {}
    with OUTPUT_JSON.open(encoding="utf-8") as handle:
        return json.load(handle)


def extract_icon(apk: Path, icon_path: str, destination: Path) -> bool:
    if not icon_path:
        return False
    try:
        with zipfile.ZipFile(apk) as archive:
            destination.write_bytes(archive.read(icon_path))
        return True
    except (KeyError, zipfile.BadZipFile):
        return False


def build_source(raw: dict) -> index_pb2.Source:
    source = index_pb2.Source(
        name=raw.get("name", ""),
        language=raw.get("lang", ""),
        homeUrl=raw.get("baseUrl", ""),
    )
    try:
        source.id = int(raw.get("id", 0))
    except (TypeError, ValueError):
        source.id = 0
    source.mirrorUrls.extend(raw.get("mirrorUrls", []) or [])
    return source


def main() -> int:
    if not APK_DIR.is_dir():
        raise SystemExit(f"APK directory not found: {APK_DIR}")

    apks = sorted(APK_DIR.glob("*.apk"))
    if not apks:
        raise SystemExit(f"no APKs found in {APK_DIR}")

    aapt = find_aapt()
    inspector_sources = load_sources()

    (REPO_DIR / "apk").mkdir(parents=True, exist_ok=True)
    (REPO_DIR / "icon").mkdir(parents=True, exist_ok=True)

    # The index is regenerated from scratch, so drop artifacts of extensions that
    # are no longer published.
    for directory in ("apk", "icon"):
        target = REPO_DIR / directory
        for old_file in target.iterdir():
            if old_file.is_file():
                old_file.unlink()

    extensions = []
    legacy_entries = []

    for apk in apks:
        text = badging(aapt, apk)
        package_line = next((line for line in text.splitlines() if line.startswith("package:")), "")
        application_line = next((line for line in text.splitlines() if line.startswith("application:")), "")

        package_name = grab(r"name='([^']+)'", package_line)
        version_code = int(grab(r"versionCode='([^']+)'", package_line, "0"))
        version_name = grab(r"versionName='([^']+)'", package_line)
        if not package_name:
            print(f"warning: could not read package name from {apk.name}", file=sys.stderr)
            continue

        name = grab(r"label='([^']+)'", application_line)
        if name.startswith("Tachiyomi: "):
            name = name[len("Tachiyomi: "):]

        nsfw = grab(r"name='tachiyomi\.extension\.nsfw' value='([^']+)'", text, "0") == "1"
        icon_path = grab(r"application-icon-320'([^']+)'", text) or grab(r" icon='([^']+)'", application_line)

        apk_name = apk.name
        destination_apk = REPO_DIR / "apk" / apk_name
        destination_apk.write_bytes(apk.read_bytes())

        extract_icon(apk, icon_path, REPO_DIR / "icon" / f"{package_name}.png")

        raw_sources = inspector_sources.get(package_name, [])
        sources = [build_source(source) for source in raw_sources]
        language = language_for(package_name) or next(
            (source.get("lang", "") for source in raw_sources if source.get("lang")),
            "all",
        )

        extension_lib = version_name.rsplit(".", 1)[0] if "." in version_name else ""

        extension = index_pb2.Extension(
            name=name,
            packageName=package_name,
            resources=index_pb2.Resources(
                apkUrl=f"{RAW_BASE}/apk/{apk_name}",
                iconUrl=f"{RAW_BASE}/icon/{package_name}.png",
            ),
            extensionLib=extension_lib,
            versionCode=version_code,
            versionName=version_name,
            contentWarning=(
                index_pb2.CONTENT_WARNING_NSFW if nsfw else index_pb2.CONTENT_WARNING_SAFE
            ),
            sources=sources,
        )
        extensions.append(extension)

        legacy_entries.append(
            {
                "name": name,
                "pkg": package_name,
                "apk": apk_name,
                "lang": language,
                "code": version_code,
                "version": version_name,
                "nsfw": int(nsfw),
                "sources": raw_sources,
            }
        )
        print(f"indexed {package_name} v{version_name} ({version_code})")

    extensions.sort(key=lambda extension: extension.packageName)
    legacy_entries.sort(key=lambda entry: entry["pkg"])

    index = index_pb2.Index(
        name=REPO_DISPLAY_NAME,
        badgeLabel="RBN",
        signingKey=SIGNING_KEY,
        contact=index_pb2.Contact(website=REPO_WEBSITE),
        extensionList=index_pb2.ExtensionList(extensions=extensions),
    )

    (REPO_DIR / "index.pb").write_bytes(
        gzip.compress(index.SerializeToString(deterministic=True), mtime=0)
    )
    (REPO_DIR / "index.json").write_text(
        json_format.MessageToJson(
            index,
            always_print_fields_with_no_presence=False,
            preserving_proto_field_name=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    (REPO_DIR / "index.min.json").write_text(
        json.dumps(legacy_entries, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (REPO_DIR / "repo.json").write_text(
        json.dumps(
            {
                "index_v2": f"{RAW_BASE}/index.pb",
                "meta": {
                    "name": REPO_DISPLAY_NAME,
                    "website": REPO_WEBSITE,
                    "signingKeyFingerprint": SIGNING_KEY,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    listing = [
        "<!DOCTYPE html>",
        "<html>",
        '<head><meta charset="UTF-8"><title>apks</title></head>',
        "<body>",
        "<pre>",
    ]
    for extension in extensions:
        listing.append(
            f'<a href="{html.escape(extension.resources.apkUrl)}">'
            f"{html.escape('Tachiyomi: ' + extension.name)}</a>"
        )
    listing.extend(["</pre>", "</body>", "</html>", ""])
    (REPO_DIR / "index.html").write_text("\n".join(listing), encoding="utf-8")

    print(f"published {len(extensions)} extension(s) to {REPO_DIR}")
    print(f"repo URL: {RAW_BASE}/index.pb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
