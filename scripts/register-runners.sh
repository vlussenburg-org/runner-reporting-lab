#!/usr/bin/env bash
# Bring up the 3 labeled self-hosted runners (azure / gcp / vm).
# Uses your current `gh` token to let the runner image self-register.
set -euo pipefail

cd "$(dirname "$0")/.."

# The myoung34/github-runner image needs a token that can mint a repo-level
# runner registration token. Your gh OAuth token (repo scope + repo admin) works.
export RUNNER_LAB_TOKEN="$(gh auth token)"

echo "Pulling runner image (multi-arch, works on Apple Silicon)..."
docker compose -f docker/compose.yml pull

echo "Starting 3 runners: azure-runner, gcp-runner, vm-runner ..."
docker compose -f docker/compose.yml up -d

echo
echo "Waiting for runners to register with GitHub..."
for i in $(seq 1 30); do
  count="$(gh api repos/vlussenburg-org/runner-reporting-lab/actions/runners --jq '.total_count' 2>/dev/null || echo 0)"
  if [ "${count:-0}" -ge 3 ]; then break; fi
  sleep 3
done

echo
echo "Registered runners:"
gh api repos/vlussenburg-org/runner-reporting-lab/actions/runners \
  --jq '.runners[] | "  \(.name)  status=\(.status)  labels=[\([.labels[].name] | join(","))]"'
