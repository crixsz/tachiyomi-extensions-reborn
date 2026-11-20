#!/usr/bin/env python3
"""Report recent keiyoushi/extensions-source commits for the extensions this repo publishes.

This repo is based on the archived tachiyomi-extensions tree, while keiyoushi now
uses a different layout, so upstream changes cannot be merged automatically.
This script only surfaces commits that touch the same sources so they can be
ported by hand.

Usage:
    check-upstream.py [since-iso8601] [--output report.md]

Environment:
    CI_MODULES        comma separated lang/name modules (default: all/nhentai,en/multporn)
    UPSTREAM_REPO     default: keiyoushi/extensions-source
    GITHUB_TOKEN      optional, raises the API rate limit
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

UPSTREAM_REPO = os.environ.get("UPSTREAM_REPO", "keiyoushi/extensions-source")
MODULES = [
    module.strip()
    for module in os.environ.get("CI_MODULES", "all/nhentai,en/multporn").split(",")
    if module.strip()
]


def api(url: str):
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"GitHub API error {error.code} for {url}") from error


def main() -> int:
    since = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    if not since:
        since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    output = Path("upstream-report.md")
    if "--output" in sys.argv:
        output = Path(sys.argv[sys.argv.index("--output") + 1])

    sections = []
    for module in MODULES:
        path = f"src/{module}"
        query = urllib.parse.urlencode({"path": path, "since": since, "per_page": 30})
        commits = api(f"https://api.github.com/repos/{UPSTREAM_REPO}/commits?{query}")
        if not commits:
            continue
        lines = [f"### `{path}`", ""]
        for commit in commits:
            message = commit["commit"]["message"].splitlines()[0]
            sha = commit["sha"][:10]
            date = commit["commit"]["committer"]["date"][:10]
            lines.append(f"- [{sha}]({commit['html_url']}) {date} — {message}")
        sections.append("\n".join(lines))

    if not sections:
        print("No upstream changes found.")
        return 0

    report = "\n\n".join(
        [
            f"Commits in [{UPSTREAM_REPO}](https://github.com/{UPSTREAM_REPO}) since {since} "
            "that touch extensions published by this repo.",
            "",
            *sections,
            "",
            "Port the relevant fixes to `master` by hand, then bump `extVersionCode` in the "
            "extension's `build.gradle` so the app offers the update.",
        ]
    )
    output.write_text(report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
