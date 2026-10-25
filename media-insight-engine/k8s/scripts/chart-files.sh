#!/usr/bin/env bash
# Copy the app's config/, prompts/ and golden/ into the chart (charts/media-insight-engine/files/), which
# turns them into ConfigMaps. Run before installing the chart from source; the release workflow runs it
# before packaging, so a published chart carries the files. files/ is gitignored.
set -euo pipefail
K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$(cd "$K8S/.." && pwd)"
DEST="$K8S/charts/media-insight-engine/files"
rm -rf "$DEST" && mkdir -p "$DEST"
cp -R "$APP/config" "$APP/prompts" "$APP/golden" "$DEST/"
echo "Copied config/, prompts/, golden/ into ${DEST#"$APP"/}"
