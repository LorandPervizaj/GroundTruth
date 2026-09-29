#!/usr/bin/env bash
# Download one exact GroundTruth GitHub Release, verify it, and install it into
# the serving paths the Dockerfile copies. Run from the repository root with
# GH_TOKEN set and the uv environment synced.
#
#   bash scripts/release/install-verified-release.sh groundtruth-release-<release_id>
#
# RELEASE_ASSETS_DIR keeps the downloaded assets for deployment evidence.
set -euo pipefail

tag="${1:?release tag required}"
if [[ ! "$tag" =~ ^groundtruth-release-[0-9A-Za-z][0-9A-Za-z._-]{0,99}$ ]]; then
  echo "invalid release tag: $tag" >&2
  exit 1
fi
release_id="${tag#groundtruth-release-}"
bundle="$tag.tar.gz"
assets_dir="${RELEASE_ASSETS_DIR:-$(mktemp -d)}"
extract_dir="$(mktemp -d)"
mkdir -p "$assets_dir"

assets="$(gh release view "$tag" --repo "$GITHUB_REPOSITORY" --json assets --jq '.assets[].name' | sort)"
expected="$(printf '%s\n' "$bundle" "$bundle.sha256" | sort)"
if [ "$assets" != "$expected" ]; then
  echo "release $tag must contain exactly $bundle and $bundle.sha256" >&2
  exit 1
fi
gh release download "$tag" --repo "$GITHUB_REPOSITORY" --dir "$assets_dir" --clobber
(cd "$assets_dir" && sha256sum --check --strict "$bundle.sha256")
uv run groundtruth release verify-bundle "$assets_dir/$bundle" --release-id "$release_id"

tar -xzf "$assets_dir/$bundle" -C "$extract_dir"
rm -rf reports/generated/lookup_cache
cp -a "$extract_dir/lookup_cache" reports/generated/lookup_cache
cp "$extract_dir/data/api/annual_report.json" data/api/annual_report.json
cp "$extract_dir/data/api/rent_yield.json" data/api/rent_yield.json
echo "installed verified release $tag"
