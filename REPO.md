# Publishing this fork as an extension repo

This repo can publish its own Mihon/Tachiyomi extension repository, in the same
format as [keiyoushi/extensions](https://github.com/keiyoushi/extensions), and the
app will offer updates from it.

## What gets published

The `CI` workflow (`.github/workflows/build_push.yml`) builds the extensions listed in
`CI_MODULES` and pushes them to the `repo` branch:

| File | Purpose |
| --- | --- |
| `index.pb` | Gzipped protobuf index (repo v2), used by current Mihon |
| `index.json` | Same index as protobuf JSON, for debugging |
| `index.min.json` | Legacy repo v1 index, for older apps |
| `repo.json` | Points the app at `index.pb` and carries the signing fingerprint |
| `apk/` | Signed extension APKs |
| `icon/` | Extension icons |

The URL to add in the app is:

```
https://github.com/crixsz/tachiyomi-extensions-reborn/raw/repo/index.pb
```

In Mihon: **More → Settings → Browse → Extension repos → Add**, paste the URL, then
open the **Extensions** tab and install.

## How in-app updates work

The app compares the `versionCode` in `index.pb` with the installed extension's
`versionCode`. To ship an update:

1. Change the extension code.
2. Bump `extVersionCode` in `src/<lang>/<name>/build.gradle`.
3. Commit and push to `master`.

The workflow rebuilds the extension, replaces `apk/`, and rewrites `index.pb` with the
new version code. The app then shows an **Update** button for it.

Extensions that are not rebuilt are not listed, so the published set is exactly
`CI_MODULES`. To add more:

```yaml
# .github/workflows/build_push.yml
env:
  CI_MODULES: "all/nhentai,en/multporn"
```

## One-time GitHub setup

The signing key was generated locally as `signingkey.jks` (gitignored). It must be
backed up: every future update must be signed with it or the app will reject the
update.

Add these four repository secrets under **Settings → Secrets and variables → Actions
→ New repository secret**:

| Secret | Value |
| --- | --- |
| `SIGNING_KEY` | contents of `signingkey.jks.base64` (one line) |
| `ALIAS` | `extensions` |
| `KEY_STORE_PASSWORD` | the store password you saved when the key was generated |
| `KEY_PASSWORD` | the key password (same value) |

Or with the GitHub CLI:

```bash
gh secret set SIGNING_KEY < signingkey.jks.base64
gh secret set ALIAS --body extensions
gh secret set KEY_STORE_PASSWORD --body '<store-password>'
gh secret set KEY_PASSWORD --body '<key-password>'
```

Signing fingerprint (already embedded in the index):

```
ec5f36ddbeae4fde1c5c9c1484b1c9dfd9ca467f9dfe8cc2c0e2bd658f859656
```

Then push to `master`. The first run creates the `repo` branch automatically.

## Keeping up with keiyoushi

`keiyoushi/extensions-source` has moved to a different project layout
(`compiler/`, `lib-multisrc/`, extension-lib 1.6, Java 25), so it cannot be merged
into this archived tree automatically. The `Upstream watch` workflow checks weekly
for keiyoushi commits under `src/all/nhentai` and `src/en/multporn` and opens/updates
an issue listing them. Port the relevant changes by hand, then bump `extVersionCode`.

You can also run the check locally:

```bash
python .github/scripts/check-upstream.py 2026-01-01T00:00:00Z
```

## Local publish test

```bash
# Build with the same modules and key as CI
CI_MODULES="all/nhentai,en/multporn" \
ALIAS=extensions \
KEY_STORE_PASSWORD='<store-password>' \
KEY_PASSWORD='<key-password>' \
./gradlew assembleRelease

# Collect the APKs
mkdir -p apk
find src -path '*/build/outputs/apk/release/*.apk' -exec cp {} apk/ \;

# Generate the repo files (needs Python protobuf)
python -m pip install --upgrade protobuf
GITHUB_REPOSITORY=crixsz/tachiyomi-extensions-reborn \
APK_DIR="$PWD/apk" \
OUTPUT_JSON="$PWD/output.json" \
REPO_DIR="$PWD/repo-out" \
CI_MODULES="all/nhentai,en/multporn" \
python .github/scripts/publish-repo.py
```

`output.json` is produced by the Tachiyomi Extensions Inspector, which the workflow
downloads automatically. Without it the index still builds, but the source lists are
empty.

## Notes and caveats

- The published extensions are signed with a **new** key, not keiyoushi's. If the
  same package was previously installed from keiyoushi, uninstall it once before
  installing this repo's version.
- Both repos can be added to the app; duplicates of the same package resolve to one
  of them. Keeping `CI_MODULES` to only your modified extensions avoids surprises.
- This fork targets extension-lib `1.4.2.1`. If a newer app refuses to install it,
  that is a library/API compatibility problem, not a repo problem.
- `signingkey.jks` and `signingkey.jks.base64` are gitignored. Never commit them.
