#!/usr/bin/env bash
# Tear down the 3 self-hosted runners and remove them from the repo.
# With ACCESS_TOKEN set, the image de-registers each runner on shutdown.
set -euo pipefail

cd "$(dirname "$0")/.."
export RUNNER_LAB_TOKEN="$(gh auth token)"

echo "Stopping + removing runner containers (auto-deregisters from GitHub)..."
docker compose -f docker/compose.yml down

echo "Remaining runners on repo:"
gh api repos/vlussenburg-org/runner-reporting-lab/actions/runners --jq '.total_count'
