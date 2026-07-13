#!/usr/bin/env python3
"""
runner-report.py — the runner usage report, built only from data GitHub exposes.

For a repo (or easily extended to an org/enterprise), it produces a monthly
breakdown of:

  HOSTED runners      -> billable minutes by OS   (from the run timing API,
                         i.e. the same numbers behind the portal usage report)
  SELF-HOSTED runners -> jobs + computed minutes, attributed to "where hosted"
                         PURELY via the runner's provider LABEL (azure/gcp/vm/...)

Key honesty baked in: GitHub does NOT know a self-hosted runner's cloud/infra.
The "provider" column is only as good as the label convention the customer uses.

Auth: shells out to `gh api`, so it uses your existing `gh` login. No tokens here.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone

# Labels we treat as a "where is it hosted" signal. Extend for the customer's
# own convention (e.g. aws, onprem, datacenter-east, ...).
PROVIDER_LABELS = {"azure", "gcp", "aws", "vm", "onprem", "datacenter"}
OS_LABELS = {"ubuntu-latest": "UBUNTU", "windows-latest": "WINDOWS", "macos-latest": "MACOS"}


def gh(path: str, paginate: bool = False, jq: str | None = None):
    cmd = ["gh", "api"]
    if paginate:
        cmd += ["--paginate"]
    cmd += [path]
    if jq:
        cmd += ["--jq", jq]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"gh api {path} failed: {out.stderr.strip()}")
    text = out.stdout.strip()
    if not text:
        return None
    if paginate and jq:
        # --paginate + --jq yields one JSON value per page/line
        return [json.loads(l) for l in text.splitlines() if l.strip()]
    return json.loads(text)


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def provider_for(labels: list[str], runner_name: str | None) -> str:
    low = {l.lower() for l in labels}
    for p in PROVIDER_LABELS:
        if p in low:
            return p
    # fall back to parsing the runner name (e.g. "azure-runner")
    if runner_name:
        for p in PROVIDER_LABELS:
            if runner_name.lower().startswith(p):
                return p
    return "unlabeled"


def collect(repo: str, since: datetime, until: datetime):
    # ---- self-hosted inventory (point-in-time) ----
    inv = gh(f"repos/{repo}/actions/runners") or {"runners": []}
    inventory = [
        {
            "name": r["name"],
            "os": r.get("os"),
            "status": r.get("status"),
            "labels": [l["name"] for l in r.get("labels", [])],
            "provider": provider_for([l["name"] for l in r.get("labels", [])], r["name"]),
        }
        for r in inv.get("runners", [])
    ]

    # ---- workflow runs in window ----
    created = f"{since.date()}..{until.date()}"
    pages = gh(f"repos/{repo}/actions/runs?created={created}&per_page=100", paginate=True, jq=".workflow_runs[]")
    runs = pages or []

    # month -> hosted OS -> total_ms ; month -> provider -> {jobs, ms}
    hosted = defaultdict(lambda: defaultdict(lambda: {"ms": 0, "jobs": 0}))
    selfhosted = defaultdict(lambda: defaultdict(lambda: {"ms": 0, "jobs": 0}))

    for run in runs:
        created_at = parse_ts(run["created_at"])
        if not (since <= created_at <= until):
            continue
        month = created_at.strftime("%Y-%m")
        run_id = run["id"]

        # Hosted billable minutes come from the timing API (portal-grade numbers).
        try:
            timing = gh(f"repos/{repo}/actions/runs/{run_id}/timing") or {}
        except RuntimeError:
            timing = {}
        for os_name, data in (timing.get("billable") or {}).items():
            hosted[month][os_name]["ms"] += data.get("total_ms", 0)
            hosted[month][os_name]["jobs"] += data.get("jobs", 0)

        # Self-hosted: no billing exists, so compute duration from job timestamps
        # and attribute to a provider via the job's labels.
        jobs = gh(f"repos/{repo}/actions/runs/{run_id}/jobs") or {"jobs": []}
        for job in jobs.get("jobs", []):
            labels = job.get("labels", []) or []
            if not any(l.lower() == "self-hosted" for l in labels):
                continue  # hosted jobs already counted via timing
            prov = provider_for(labels, job.get("runner_name"))
            start, end = job.get("started_at"), job.get("completed_at")
            ms = 0
            if start and end:
                ms = max(0, int((parse_ts(end) - parse_ts(start)).total_seconds() * 1000))
            selfhosted[month][prov]["ms"] += ms
            selfhosted[month][prov]["jobs"] += 1

    return inventory, hosted, selfhosted


def mins(ms: int) -> float:
    return round(ms / 60000, 1)


def render_text(repo, since, until, inventory, hosted, selfhosted) -> str:
    L = []
    L.append(f"Runner Report — {repo}")
    L.append(f"Window: {since.date()} .. {until.date()}")
    L.append("")
    L.append("Self-hosted runner inventory (current):")
    if inventory:
        for r in inventory:
            L.append(f"  - {r['name']:<16} provider={r['provider']:<10} status={r['status']:<8} labels={r['labels']}")
    else:
        L.append("  (none registered)")
    L.append("")

    months = sorted(set(hosted) | set(selfhosted))
    for m in months:
        L.append(f"== {m} ==")
        L.append("  HOSTED (billable minutes by OS — same source as portal report):")
        if hosted.get(m):
            for os_name, d in sorted(hosted[m].items()):
                L.append(f"    {os_name:<10} {mins(d['ms']):>8} min   ({d['jobs']} jobs)")
        else:
            L.append("    (none)")
        L.append("  SELF-HOSTED (computed minutes, attributed by provider LABEL):")
        if selfhosted.get(m):
            for prov, d in sorted(selfhosted[m].items()):
                L.append(f"    {prov:<10} {mins(d['ms']):>8} min   ({d['jobs']} jobs)")
        else:
            L.append("    (none)")
        L.append("")
    if not months:
        L.append("(no workflow runs in window)")
    L.append("NOTE: 'provider' for self-hosted is derived ONLY from labels/runner names —")
    L.append("GitHub has no native visibility into the underlying VM/cloud.")
    return "\n".join(L)


def render_md(repo, since, until, inventory, hosted, selfhosted) -> str:
    L = [f"# Runner Report — `{repo}`", "", f"**Window:** {since.date()} .. {until.date()}", ""]
    L.append("## Self-hosted inventory")
    L.append("| Runner | Provider (from label) | Status | Labels |")
    L.append("|---|---|---|---|")
    for r in inventory or []:
        L.append(f"| `{r['name']}` | {r['provider']} | {r['status']} | {', '.join(r['labels'])} |")
    if not inventory:
        L.append("| _(none)_ | | | |")
    L.append("")
    months = sorted(set(hosted) | set(selfhosted))
    for m in months:
        L.append(f"## {m}")
        L.append("**Hosted — billable minutes by OS** (portal-grade source)")
        L.append("")
        L.append("| OS | Minutes | Jobs |")
        L.append("|---|--:|--:|")
        for os_name, d in sorted(hosted.get(m, {}).items()):
            L.append(f"| {os_name} | {mins(d['ms'])} | {d['jobs']} |")
        L.append("")
        L.append("**Self-hosted — computed minutes by provider label**")
        L.append("")
        L.append("| Provider | Minutes | Jobs |")
        L.append("|---|--:|--:|")
        for prov, d in sorted(selfhosted.get(m, {}).items()):
            L.append(f"| {prov} | {mins(d['ms'])} | {d['jobs']} |")
        L.append("")
    L.append("> Self-hosted `provider` is derived only from labels/runner names. "
             "GitHub has no native visibility into the underlying VM/cloud.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default="vlussenburg-org/runner-reporting-lab")
    ap.add_argument("--since", required=True, help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--until", required=True, help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--format", choices=["text", "md", "json"], default="text")
    args = ap.parse_args()

    since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    until = datetime.strptime(args.until, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)

    inventory, hosted, selfhosted = collect(args.repo, since, until)

    if args.format == "json":
        print(json.dumps({
            "repo": args.repo,
            "window": {"since": args.since, "until": args.until},
            "inventory": inventory,
            "hosted": {m: dict(d) for m, d in hosted.items()},
            "self_hosted": {m: dict(d) for m, d in selfhosted.items()},
        }, indent=2))
    elif args.format == "md":
        print(render_md(args.repo, since, until, inventory, hosted, selfhosted))
    else:
        print(render_text(args.repo, since, until, inventory, hosted, selfhosted))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
