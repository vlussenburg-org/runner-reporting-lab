# Runner Reporting Lab

A hands-on lab answering a real customer question:

> "We want a report on our GitHub Runners — **Hosted and Self-Hosted** — like the
> basic portal reports, **plus where the self-hosted runners are hosted (VM, GCP,
> Azure, …)**, for April, May and June."

Short answer, proven below:

| What they want | Can GitHub give it? | How |
|---|---|---|
| Hosted runner minutes by OS / size / type | ✅ **Yes, natively** | Actions **Usage Metrics** dashboard (org/enterprise) + **Billing usage API** (`/settings/billing/usage`, month-sliceable) + per-run **timing API** |
| Self-hosted runner inventory | ✅ Yes | `GET /{scope}/actions/runners` → name, os, **labels**, runner group, status |
| Self-hosted **minutes** | ⚠️ Compute it yourself | Not billed/tracked. Derive from job `started_at`/`completed_at` |
| Self-hosted **"where hosted" (VM/GCP/Azure)** | ❌ **Not natively** | **Only** via a **label** or **runner-group naming** convention the customer controls |

**The crux:** GitHub bills nothing for self-hosted compute and has **zero visibility
into the underlying infrastructure**. All it ever sees about a self-hosted runner is
its `name`, `os`, `labels`, `runner_group`, and `status`. So "is this runner on Azure
or GCP?" is answerable **only if you encode that in labels or runner groups**.

---

## How this lab proves it

Three **self-hosted runners run as Docker containers on one laptop**, each labeled with
a fake "provider":

| Container | Label | Pretends to be |
|---|---|---|
| `azure-runner` | `azure` | an Azure VM |
| `gcp-runner` | `gcp` | a GCP instance |
| `vm-runner` | `vm` | an on-prem VM |

They are physically identical. The *only* thing that lets a report say "this ran on
Azure" is the label — which is exactly the mechanism the customer would use at scale.

- [`.github/workflows/hosted.yml`](.github/workflows/hosted.yml) — GitHub-hosted jobs (ubuntu + windows) to generate real hosted usage.
- [`.github/workflows/self-hosted.yml`](.github/workflows/self-hosted.yml) — one job per provider label.
- [`docker/compose.yml`](docker/compose.yml) — the 3 labeled runners.
- **[`prompts/runner-report.prompt.md`](prompts/runner-report.prompt.md) — the report generator: a prompt you paste into Copilot CLI (works at repo/org/enterprise scope).**
- [`scripts/runner-report.py`](scripts/runner-report.py) — _optional_ deterministic equivalent of the prompt, for CI/scheduled runs.

---

## Run it

```bash
# 1. Bring up the 3 labeled self-hosted runners (uses your gh login)
scripts/register-runners.sh

# 2. Trigger the workflows
gh workflow run hosted.yml      -R vlussenburg-org/runner-reporting-lab
gh workflow run self-hosted.yml -R vlussenburg-org/runner-reporting-lab

# 4. Tear the runners down (auto-deregisters from GitHub)
scripts/deregister-runners.sh
```

**3. Build the report — paste [`prompts/runner-report.prompt.md`](prompts/runner-report.prompt.md)
into Copilot CLI** (edit the SCOPE / TARGET / WINDOW inputs first). The agent hits the GitHub APIs
itself and returns the finished Markdown report — no script to run. See
[`SAMPLE-REPORT.md`](SAMPLE-REPORT.md) for the shape of the output.

> Prefer a deterministic, schedulable version? `scripts/runner-report.py --since … --until … --format md`
> produces the same report programmatically.

> Self-hosted runners are **outbound-only** (they long-poll GitHub), so no inbound
> networking / Tailscale funnel is required to register or run them.

---

## What each data source actually returns

- **Actions Usage Metrics dashboard** (org/enterprise Insights): the "portal report"
  the customer means — minutes by runner type, OS, and larger-runner size. **Team/Enterprise only.**
- **Billing usage API** `GET /orgs/{org}/settings/billing/usage?year=&month=`: line items
  per SKU (`Actions` product, runner size, OS), with cost-center attribution — this is
  what you slice into **April / May / June** and hand to finance.
- **Run timing API** `GET /repos/{o}/{r}/actions/runs/{id}/timing`: `billable` minutes
  per OS for a single run (what the report script sums for hosted).
- **Runners API** `GET /{scope}/actions/runners`: self-hosted inventory + labels.
- **Jobs API** `GET /repos/{o}/{r}/actions/runs/{id}/jobs`: per-job `runner_name`,
  `runner_group_name`, `labels`, and timestamps → the only place to attribute
  self-hosted work to a "provider".

---

## Recommendations for the customer

1. **Hosted:** use the Usage Metrics dashboard for the portal view and the billing
   usage API for the monthly Apr/May/Jun export. Already fully available.
2. **Self-hosted location:** adopt a **label convention** (`azure`, `gcp`, `onprem`, …)
   and/or **runner groups named by provider** (they're on Enterprise, so runner groups
   are available). Without this, "where hosted" is unanswerable from the GitHub side.
3. **Self-hosted minutes:** if they want cost-style numbers, compute duration from job
   timestamps (as this script does) — GitHub does not meter self-hosted compute.

## Caveats

- Testing now can't backfill real Apr–Jun data; the script is date-parameterized and
  runs against whatever window you pass. The **shape** of the report is the deliverable.
- Runner **inventory** is point-in-time (current runners), not historical.
- This lab is repo-scoped for simplicity; the same calls exist at **org** and
  **enterprise** scope, which is how a large EMU customer (many orgs) would run it centrally.


## Live sample report

See [SAMPLE-REPORT.md](SAMPLE-REPORT.md) for real output from this lab (3 labeled Docker runners + hosted jobs).
