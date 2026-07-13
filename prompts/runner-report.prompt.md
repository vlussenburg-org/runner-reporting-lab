# Prompt — GitHub Runner Usage Report (Hosted + Self-Hosted, with "where hosted")

Paste this into **Copilot CLI** (or any agent with `gh`/GitHub MCP access) to generate a
runner report for a customer. It answers: *hosted vs self-hosted usage by month, plus
where each self-hosted runner is hosted (VM/GCP/Azure/…)* — using only data GitHub exposes.

> Fill in the inputs at the top, then send.

---

## Inputs (edit these)
- **SCOPE**: `repo` | `org` | `enterprise`
- **TARGET**: e.g. `owner/repo`, or `my-org`, or `my-enterprise-slug`
- **WINDOW**: `2026-04-01` .. `2026-06-30`
- **PROVIDER LABELS** (the customer's "where hosted" vocabulary): `azure, gcp, aws, vm, onprem`
  — note runners can carry **multiple labels** at once (e.g. `azure,eastus2,team-payments,vm-size-D4s`),
  so the same data can also be sliced by region/team/size if those labels exist.

---

## Prompt

You are generating a GitHub Actions **runner usage report** for the scope **{SCOPE} = {TARGET}**,
covering **{WINDOW}**. Use `gh api` (or GitHub MCP). Do the work yourself and output the final
report — do not write a script. Be rigorous and honest about what GitHub can and cannot tell us.

**Ground truth you must respect:**
- GitHub **bills nothing** for self-hosted compute and has **zero native visibility** into the
  underlying infrastructure. The ONLY signal for "where a self-hosted runner is hosted" is its
  **labels** or **runner-group name** — a convention the customer controls. Never invent a
  provider; if a runner has no provider label, report it as `unlabeled`.
- On **public** repos, hosted `billable` minutes are `0` (minutes are free). On private/EMU repos
  the `billable` numbers are populated — that is the portal/billing figure.
- Self-hosted "minutes" don't exist as a metric; **compute** them from each job's
  `started_at`/`completed_at`.

**Steps:**

1. **Self-hosted inventory (point-in-time).** List runners for the scope:
   - repo → `GET /repos/{owner}/{repo}/actions/runners`
   - org → `GET /orgs/{org}/actions/runners`  (needs `admin:org` / runners permission)
   - enterprise → `GET /enterprises/{ent}/actions/runners`
   For each runner record `name`, `os`, `status`, `labels`, and derive **provider** = first of the
   PROVIDER LABELS found in its labels (else parse the runner name, else `unlabeled`).

2. **Workflow runs in window.** Runs only exist at repo scope:
   `GET /repos/{owner}/{repo}/actions/runs?created={since}..{until}&per_page=100` (paginate).
   For **org/enterprise** scope, first enumerate repos (`GET /orgs/{org}/repos`) and repeat per repo,
   OR use the billing usage API in step 5 for the hosted monthly totals.

3. **Per run — hosted billable.** `GET /repos/{owner}/{repo}/actions/runs/{id}/timing` →
   `billable` gives `{UBUNTU|WINDOWS|MACOS: {total_ms, jobs}}`. Sum `total_ms` by OS by month.

4. **Per run — jobs.** `GET /repos/{owner}/{repo}/actions/runs/{id}/jobs`. For each job:
   - If its `labels` contain `self-hosted`: attribute to a **provider** (labels → runner name),
     add `completed_at - started_at` to that provider's minutes, and record the `runner_name` in a
     **"runners seen in window"** set (this survives ephemeral runners that have since exited).
   - Else (hosted): add elapsed to that OS's wall-clock, and count the job.

5. **Hosted monthly totals at scale (org/enterprise).** For the portal/billing numbers, call the
   enhanced billing usage API and slice by month:
   - org → `GET /orgs/{org}/settings/billing/usage?year={y}&month={m}`
   - enterprise → `GET /enterprises/{ent}/settings/billing/usage?year={y}&month={m}`
   Filter line items to the `Actions` product; group by runner size/OS. (Also mention the
   **Actions Usage Metrics** dashboard under Insights — Team/Enterprise only, UI-only — as the
   native "portal report".)

6. **Aggregate by calendar month** (from each run's `created_at`) and **render Markdown**:
   - A **"Self-hosted runners currently registered"** table (name, provider, status, labels).
   - A **"Self-hosted runners seen in window"** table (name, provider, job count).
   - Per month: **Hosted by OS** (Billable min | Elapsed min | Jobs) and
     **Self-hosted by provider** (Minutes | Jobs).
   - A short **Notes** block restating: provider is label-derived only (no native infra visibility);
     hosted billable is 0 on public repos; self-hosted minutes are computed, not billed.

7. **Close with 2–3 recommendations**, e.g.: adopt a **multi-label convention** on each self-hosted
   runner (set at registration, e.g. `--labels azure,eastus2,team-payments,vm-size-D4s`) so "where
   hosted" — and region/team/size — become reportable; prefer labels over runner groups for
   reporting flexibility; use the billing usage API for the monthly hosted export; note that
   self-hosted has no native cost metric.

Output only the finished report.
