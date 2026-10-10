# Operations reliability — paper only

The v8 ledger is an append-only event record. Never backfill missed evaluations
with prices that were not observed at the intended time, edit old events,
or conflate historical v9 backtests with prospective paper results.

## Why this patch exists

On 2026-10-08, the public derived report recorded 105 closed experiments
and **98 delayed (>30 min) closes**. The main issue is not insufficient trade
volume: the scheduled paper workflow had long gaps. Those delayed outcomes
are retained as historical observations and excluded from timely learning.
More overlapping entries without a reliable clock would worsen the research.

## New fail-safe policy

1. Prefer confirmed, responsive OKX swap tickers when *opening new*
   experiments. Existing trades **always exit using their original
   exchange, instrument and market type**; this is never overridden.
2. **Three GitHub-native clocks**, all on the default `main` branch:
   - [Paper workflow](.github/workflows/lab.yml) at UTC minutes
     `:04, :14, :24, :34, :44, :54` (target one observation each 10 min).
   - [Redundant recovery](.github/workflows/rescue.yml) at
     `:02, :12, :22, :32, :42, :52`.
   - [Ledger health guardian](.github/workflows/health.yml) at
     `:09, :19, :29, :39, :49, :59`.
   These schedules are deliberately staggered rather than all starting
   at the top of an hour. Updating the original primary `cron` also
   re-registers the workflow's scheduled actor. None of these clocks is
   guaranteed by GitHub; they share GitHub Actions infrastructure.
3. At each successful market run, record `scheduling_diagnostics` in the
   *derived report*. `prior_observation_gap_minutes` is measured from the
   last successfully committed market report. It is not the actual time
   the cron was intended to fire.
4. After a gap >45 minutes, **new entries are throttled to at most two**
   per recovery run, while all due exits are still attempted. The next
   on-time run resumes normal selection automatically. This rule only
   affects future experiments; all old OPEN/CLOSE entries and their hashes
   are preserved.
5. **Serialized authenticated recovery, no outside service:**
   - Both recovery workflows run `scheduler_guard.py --recover` with
     their repository-scoped builtin `GITHUB_TOKEN` and minimal GitHub
     permissions (`contents:read`, `actions:write`).
   - Both share the SAME repository-wide concurrency group
     `schedule-guardian-main`; this prevents simultaneous recovery
     attempts from the two workflow definitions.
   - If the most recent canonical `main` report is older than
     **14 minutes**, the guardian checks actual `lab.yml` runs.
     It refuses to trigger when one is in flight, stuck, or recently
     started (12-minute cooldown). A canonical paper job may now run
     for up to **85 minutes** when a missed-cron recovery window is
     active; an in-flight job is classified as truly stuck only after
     **100 minutes** from the workflow run creation timestamp. This
     avoids false stuck alerts during a valid six-pulse recovery, while
     still surfacing real stalls. Immediately before a POST, it
     fetches the canonical report and run queue AGAIN to avoid
     dispatching based on obsolete information.
   - Each guardian runs an event-chain audit before the decision. Just
     before the strict `health.py` check, it fetches and checks out the
     **latest main commit**. This prevents a false stale alarm if the paper
     workflow committed a new report after the guardian first checked out.
     Reports actually older than **75 minutes** still fail; accepting a
     dispatch is not treated as proof of a fresh market observation.
   - Additional triggers: `health.yml` wakes after completed paper
     lab runs; `rescue.yml` wakes after completed `main` CI or research
     runs. The privileged `workflow_run` gate refuses events from
     foreign repositories and pull requests.
   - No external PAT, exchange trading credentials, external cron,
     synthetic backfilled trade observations or live exchange orders.
     An all-GitHub scheduler outage STILL blocks all three clocks; an
     independent host would be required to avoid that shared failure mode.
6. Run the full regression suite on CI pushes and PRs. Paper ticks run
   a targeted set of offline lifecycle tests plus full ledger audit;
   this avoids repeatedly running heavy historical research tests.

## Bounded catch-up of real-time observations (new)

A single healthy GitHub cron execution cannot make up for all the
observations missed during a multi-hour outage. After a **verified initial
paper run** with a previous report gap >45 minutes, `lab.yml` now holds
its *existing canonical ledger concurrency lock* for a maximum of six more
current-time paper observations, separated by 10 minutes each. Each observation
replays and audits the entire event history, fetches a **fresh** same-venue
market snapshot, and commits only new derived report/state and append-only
events to Git. The next primary run may queue and must not write concurrently.

Recovery windows are **not** started on ordinary healthy runs; the first
new report must already have been committed, have `recovery_throttled=true`,
and be no more than 10 minutes old. Total additional idle time is capped
at about 60 minutes per degraded job; job timeout is 85 minutes. On a missing
or invalid quote, unsafe git state, failed audit, or conflict with concurrent
Git changes, the job fails without inventing backfilled prices or force-pushing
the ledger.

No recursive dispatch loops, no always-on services, and no external schedulers.
This improves *coverage after a successful late tick*, not the probability
that GitHub launches that first tick. Scheduled workflows can still be dropped.

## Honest rolling schedule reliability estimate (new)

Each successful market report now retains at most **72 measured intervals**
between its own verified timestamp and the previous committed report. The
report publishes `estimated_missed_10m_slots` and
`estimated_10m_slot_coverage`. We count each observed interval as one
successful 10-minute slot, estimate missing slots from its elapsed time,
and allow three minutes of clock jitter. The dashboard does not present
the percentage until at least 12 observations exist. This is an **estimated
observation-slot coverage**, not GitHub workflow uptime or statistically
independent trading outcomes. A prolonged outage remains visible for at
least the next 72 measured intervals.

A second check is available through `python health.py --max-hours 1.25`.
Its `schedule_quality` field is `INSUFFICIENT_SAMPLE`, `BELOW_TARGET`,
or `ON_TARGET`; the code does not claim high availability solely from a
single new run.

The repository is public and uses a **standard Ubuntu GitHub-hosted runner**;
GitHub documents that such usage is free. It nonetheless consumes shared
capacity, so bounded sessions are used instead of running a runner asleep
24/7. If the repository becomes private or switches to a larger runner,
review GitHub billing before keeping these long recovery windows enabled.

## Expected operating indicators

With no underlying platform delays, the primary requests **6 paper ticks/hour**
and each guardian requests **6 checks/hour**; the paper `workflow_run`
completion can produce additional read-only guardian checks. The new recovery
guard is not a guarantee of precisely 10-minute observations: evaluate
`data/report.json.timestamp`, `scheduling_diagnostics.prior_observation_gap_minutes`,
`closed_this_run`, and `late_closed_this_run`, and inspect the workflow event
(`schedule` versus `workflow_dispatch`) in the GitHub Actions history.

This approach increases Github-hosted workflow executions (and may consume
Actions quotas for private or metered runners). Re-evaluate frequency if usage,
rate limits or repository size become problematic. A failed market provider,
bad ledger, GitHub outage, disabled schedules, token-permission change, or
persistent `STUCK_RUN` needs investigation rather than unbounded retry.

## Optional more reliable clock (manual setup outside repository)

If lateness remains a problem, use an **independent scheduler** (trusted
cron service or your own always-on host) to call the GitHub Actions
`workflow_dispatch` endpoint every 10 minutes. Keep the native GitHub
cron as a fallback; repository workflow concurrency prevents simultaneous
canonical ledger writes. An external service may improve trigger
reliability but cannot guarantee that GitHub's runner queue is punctual.

POST to:
`https://api.github.com/repos/0xzein-eth/crypto-strategy-lab/actions/workflows/lab.yml/dispatches`

JSON body:
`{"ref":"main"}`

Headers:
`Authorization: Bearer <PRIVATE_FINE_GRAINED_TOKEN>`
`Accept: application/vnd.github+json`
`X-GitHub-Api-Version: 2022-11-28`

Use a **fine-grained token** scoped only to this repository, with
**Actions: write** permission. Store it *only* in the external scheduler's
secret vault (never in code, Issues, workflow YAML or chat). Rotate
credentials if exposed. Do not configure any trade API keys. This step
requires repository-owner action and has **not** been configured by code.

A trusted external service could alternatively emit the
`repository_dispatch` event `paper-tick` with the appropriate token.
The workflow responds to that event but **no public unauthenticated
endpoint** can perform a dispatch.

## Check results (not guesses)

- `data/report.json` — `timestamp`, `scheduling_diagnostics`,
  `closed_this_run`, `late_closed_this_run`, `eligible_perpetual_timely.n`
- `data/events/` — canonical full chain; do not rewrite it
- `python engine.py --verify-only`, `python audit.py`
- `python -m unittest discover -s tests -v`
- GitHub `Actions` tab — both scheduled and manual/push-triggered runs

If `scheduling_diagnostics.recovery_throttled` stays true over repeated
runs, investigate GitHub scheduling and API availability. Do not lower the
integrity criteria merely to make a dashboard look profitable.


## Scheduler-quality-aware sampling and pending recovery

After at least 12 real report-to-report intervals, the live paper engine
uses the rolling best-effort 10-minute slot coverage estimate solely to
cap **NEW** entries: below 40% coverage, at most 3; from 40% to below
75%, at most 7; otherwise the usual requested budget (normally 14).
A freshly recovered >45 minute gap still caps new entries at 2, regardless
of the rolling estimate. Due exits run FIRST and are never blocked by this
entry rule. This is a sample quality safeguard, not a promised SLA.

Both guardian workflows now persist a timestamped receipt of their
GitHub-API schedule decision. If a report is older than 75 minutes but
the guardian has **just** requested a recovery or verified an active
not-stuck lab run, the next health step still audits the full event chain
and emits `DEGRADED_RECOVERING` (with a GitHub Actions warning), NOT
`health=OK`. The receipt expires after five minutes. Absent/expired
receipts, cooldowns, corrupt ledgers, or stuck workers cause a failing
check as before. A dispatch alone is never treated as a fresh quote.
This avoids misleading recovery-workflow failures immediately after a
legitimate dispatch while preserving visibility of true outages.

No workflow in this repository can guarantee GitHub's own scheduled
delivery or 90% uptime. The real rolling coverage metric must improve
before such a target can be claimed; an independent scheduler would
be required to remove the shared GitHub Actions failure domain.


## Adaptive long recovery after multi-hour GitHub scheduling gaps (2026-10-10)

Rolling schedule quality reached approximately **29.5%** over 67 recorded
intervals, including repeated missed observation gaps exceeding two to
four hours. A previous **six-pulse / one-hour** recovery did not cover
those gaps. To improve observed continuity using GitHub alone, the
verified-after-gap recovery window now dynamically budgets:

- Below 40% measured slot coverage: **18 new observations over 3 hours**.
- From 40% to below 75%: **12 new observations over 2 hours**.
- At least 75%, or insufficient history (<12 intervals): **6 new
  observations over 1 hour**.

Every observation still uses a fresh same-venue public ticker and the
same serialized ledger concurrency lock, verifies the append-only hash
chain, and commits separately. All due exits run first. New entries
remain quality-throttled. An ordinary on-time run does **not** start a
long window; a verified preceding >45-minute gap is required. A new
runner cannot create historical observations for skipped time.

Maximum job timeout is 210 minutes, safely longer than the 180-minute
maximum window. Guardian distinguishes legitimate in-flight recovery
up to 230 minutes from stalled workers; its health status remains
`DEGRADED_RECOVERING` when persisted observations are stale.

**Trade-off:** holding a GitHub-hosted runner for hours consumes more
Actions compute and queued schedules can be coalesced; it does NOT
guarantee that GitHub starts the first job or delivers 90% coverage.
Future reliability claims must be based on measured report-to-report
intervals, not the intended cron configuration.
