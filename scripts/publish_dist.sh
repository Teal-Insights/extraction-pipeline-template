#!/usr/bin/env bash
# Publish the committed dist/ tree to the GitHub repository named by
# DIST_METADATA.repository_url. Clone that repository, rsync dist/ over its
# contents, and push main.
set -euo pipefail

root=$(git rev-parse --show-toplevel)
cd "$root"

for tool in git gh rsync tar uv; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Required tool not on PATH: ${tool}" >&2
    exit 1
  fi
done

if [[ ! -d dist ]] || [[ -z "$(git ls-files -- dist)" ]]; then
  echo "No committed dist/ to publish. Generate the package and commit dist/ before running scripts/publish_dist.sh." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain -- dist)" ]]; then
  echo "dist/ has uncommitted changes. Commit dist/ before publishing." >&2
  exit 1
fi

slug=$(
  uv run python -c "from src.pipeline_config import load_pipeline_config; print(load_pipeline_config().dist_metadata.repository_slug() or '')"
)
if [[ -z "${slug}" ]]; then
  echo "No GitHub repository_url configured in DIST_METADATA; refusing to publish." >&2
  exit 1
fi

sha=$(git rev-parse HEAD)
origin_url=$(git remote get-url origin)
origin_slug=$(
  printf '%s\n' "${origin_url}" | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git/?$##'
)
if [[ -z "${origin_slug}" || "${origin_slug}" == "${origin_url}" ]]; then
  echo "Cannot parse origin remote as a GitHub repository: ${origin_url}" >&2
  exit 1
fi

stage=$(mktemp -d)
cleanup() {
  rm -rf "${stage}"
}
trap cleanup EXIT

git archive --format=tar HEAD dist | tar -x -C "${stage}"
gh repo clone "${slug}" "${stage}/target" -- --depth 1

rsync -a --delete --exclude ".git/" "${stage}/dist/" "${stage}/target/"

git -C "${stage}/target" add -A
if git -C "${stage}/target" diff --cached --quiet --exit-code; then
  echo "No changes to deploy."
  exit 0
fi

git -C "${stage}/target" commit -m "Deploy generated package from ${origin_slug}@${sha}"
git -C "${stage}/target" push origin HEAD:main
echo "Published ${origin_slug}@${sha} to ${slug} ($(git -C "${stage}/target" rev-parse --short HEAD))"
