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


## Duplicate-interval correction to observed 10m schedule coverage

Previously each report-to-report gap counted as a successful ten-minute
slot, including fast sequential runs only seconds apart during a
guardian/paper recovery collision. This inflated coverage without
representing distinct time slots. The rolling estimator now excludes
**sub-five-minute gaps** from the successful-slot numerator (but keeps
them visible in the complete bounded gap history). It reports both
`near_duplicate_fast_intervals` and
`estimated_distinct_10m_observation_intervals`, plus the older
`recent_observed_intervals` count for backward-compatible diagnostics.

Long genuine gaps still contribute all estimated missed slots and stay
visible for 72 gaps; no missed price is backfilled. This is a
timestamp-gap proxy rather than a formally certified ten-minute slot
accounting or scheduler SLA. Any lower displayed coverage immediately
after the change is a **measurement correction**, not proof that
GitHub uptime itself deteriorated.


## Quality-first horizon sampling and superseded recovery

After at least 12 DISTINCT report-to-report observation intervals, new
paper experiments pre-register shorter or longer fixed evaluation
horizons based on the *observed* 10-minute schedule coverage. Below
40%, newly opened trades use 4/8/12/24h horizons; from 40% to below
75%, new trades use 2/4/8/12/24h; at 75% or above all 1/2/4/8/12/24h
horizons are available. Insufficient history retains all six horizons.
This change does **not** alter, cancel, rewrite or prematurely exit
existing trades. The allowed horizon set is frozen into the new OPEN
evidence; no P&L-driven horizon selection or real orders are added.

When recovery sees two CONSECUTIVE real, independently committed newer
canonical market reports, it yields its long-running runner slot early
(`RECOVERY_SUPERSEDED_BY_FRESH_MAIN`). This optimization avoids occupying
GitHub compute after another canonical observer clearly takes over.
It never counts another observer's commit as its own fresh quote or
uses a synthetic historical observation. GH Actions remains a best-effort
scheduler, and source outage recovery is still not a real-time SLA.


## Continuous-on-fresh-tick sampling window (2026-10-12)

The canonical lab now starts a bounded serialized 10-minute observation
window after **any genuine newly committed recent paper tick**, not only
after a 45-minute outage. It retains the existing 6 / 12 / 18 pulse
adaptive budgets based on observed scheduler quality, and checks/fetches
authoritative `main` before each new observation. Each real quote is
validated, appended to the same immutable SHA-256 paper event ledger, and
committed independently, so an interrupted runner cannot erase already
published experimental observations. Two consecutive independent
remote advances terminate the idle run.

This can maintain one-to-three hours of observations without waiting
for further GitHub cron events, but it is **not an SLA and cannot exceed
100% slot coverage**. Missed GitHub runner starts, runner termination,
blocked exchange APIs, API quotas and GitHub's pending-job coalescing
can still create gaps. Frequent long-running Actions jobs consume
hosted compute; this repository is public, but fair-use and platform
limits still apply. The rolling measured 10-minute coverage remains
the source of truth. No exchange credentials/orders/fills are used.

Paper entries on healthy schedules now target up to 20 per observation.
However the entry-quality gate limits to 5 when coverage is below 40%,
10 when coverage is 40%–75%, and 3 when recovering from a >45-minute
gap. Due positions are always evaluated before new entries; short
horizons remain disabled for lower-quality schedule bands.

Historical v9 research now requests 400 deterministic fixed-parameter
variants per research run (previously 260 requested / ~250 available)
and two separate daily collection/evaluation runs. This increases the
breadth of **exploratory** historical screening, not statistical power
from independent regimes. It adds no auto-promotion and preserves the
full settled-funding and out-of-sample criteria; larger multiple-testing
searches are intrinsically more likely to show chance-only winners.


**Research variant validity check:** The old v9 five-horizon parameter
grid had only 250 total possible variants, so raising the workflow's
`--max-variants` parameter alone would have had no effect. The expanded
six-horizon and deterministic pre-registered parameter grid has 420
distinct catalogued variants, of which each scheduled v9 run tests the
first 400. These are exploratory **hypothesis comparisons**, not 400
independent tests or confirmed signals. The multiple-comparison
problem becomes harder, not easier, as more candidates are screened.


## Signal-slot correlation and runner-start reduction (2026-10-13)

A ten-minute observation cadence can produce two hypothetical OPEN
experiments per symbol during a single 15-minute indicator/candle
decision slot. These are not fresh independent signal hypotheses.
The paper sampler now uses a deterministic symbol/15m UTC signal-slot
index over the immutable original OPEN entries and refuses another
OPEN for the same symbol/slot. It freezes the slot at selection
(`evidence.signal_slot_utc`), with historical records retaining their
original created_at-based legacy interpretation. It never prevents
quotes being recorded at 10-minute frequency or due CLOSE attempts.

The independent signal-slot guard reduces correlated repeats even
if a very short paper experiment has already closed. A corresponding
pre-index of active symbol counts and strategy/horizon/venue signatures
reduces repeated scans of the expanding ledger. Offline regression
tests cover overlapping 10-minute observations, already-closed
positions and slot rollover.

When rolling 10m slot coverage remains below 75%, the bounded
continuous runner now requests the full maximum 18 real-time pulses
instead of 12 in the 40–75% band. The intent is to avoid one
otherwise unreliable GitHub cron restart each two-hour window.
This intentionally consumes longer GitHub-hosted compute and remains
capped at 210 minutes per job. It should only be deemed successful
if actual rolling coverage improves; Github schedule delivery
cannot be promised.

## Coverage-95 and 500-variant research expansion (2026-10-13)

Design baseline was 88.31% estimated rolling observation coverage (9
missed slots). The runner now takes 18 future real 10-minute samples
while measured coverage remains below 95%, or 12 above 95%. This
reduces reliance on frequent best-effort GitHub cron restarts, but
neither 90% nor 100% uptime is guaranteed. No missed quote is
fabricated and every new observation is SHA-256 ledger-audited.

Healthy paper entry requests increase from 20 to 24 per tick, subject
to the same cadence-based quality throttle, asset/15-minute-signal-slot
deduplication, provider identity, per-asset and UTC-day quotas, and
open-position limits. Due CLOSEs are always attempted first.

Historical v9 expands to 500 deterministic versioned parameter tests
on verified perpetual OHLCV with settled funding where available.
Repeatedly screened outcomes are NOT an untouched final holdout.
Beyond the initial 0.10% fees and 0.12% estimated friction, we
report an additional +0.25% round-trip friction sensitivity on UTC-day
means, with a separate funding-inclusive stress mean. Manual code
review eligibility now requires both stressed metrics to clear
strict positive thresholds, along with the existing purge, controls,
funding coverage and barrier constraints. No real orders or
automatic strategy activation.


## GitHub scheduling handoff and data-quality gates (2026-10-14)

The main schedule guardian now accepts a `workflow_run`-triggered
`--handoff-run-id` only for a recent successful completed main lab
run, verified against the authoritative GitHub workflow-runs API.
When the current report is less than 14m old, measured rolling coverage
is below 90% over >=12 intervals, the completion is <15m old, and no
primary run is queued or running, it requests one next
`workflow_dispatch`. A second API read immediately before dispatch
prevents most concurrent-queue races. This aims to reduce multi-hour
cron gaps, but Github scheduling is not an SLA. Avoid treating an
accepted dispatch as a collected market observation. There is no
external scheduler/credential, backfill or real exchange trade.
Guardian health now calls rolling 90% coverage the operational target;
below 90% is correctly marked BELOW_TARGET.

Real research diversification counts frozen OPEN metadata in the same
UTC day (sector + 24h price-direction + volatility band), never close
P&L or future regimes. Underrepresented strata are visited first in
a deterministic round-robin, subject to venue/source and the existing
one-symbol-per-15m-slot guard. Reports state the true number of eligible
UTC entry days, two-direction day coverage, sector and daypart breadth,
while warning that linked crypto assets are not independent trials.

`learner.py` can downweight a repeatedly poor arm only when 7
training days, 50 training closes, a negative clipped day-level upper
bound and underperformance vs the original CTRL pass simultaneously.
Monitoring/holdout scores cannot influence decisions, no arm is
removed, and the precommitted minimum control sampling stays >=20%
when offered. Do not infer live tradability from any exploratory gain.


## Incident fix: empty real-price sampling and diagnostic resilience

Root-cause audit (October 15, 2026) showed `DATA_UNAVAILABLE: all
public market sources failed: {}` can arise with **no public requests**
when every position is not due and no symbol passes the predeclared
entry gate. The idle-observation heartbeat attempts only real current
public BTC/ETH/SOL/XRP quotes, without adding or changing immutable
trade events. If the source cannot actually be verified the tick fails
closed. The report separately freezes whether heartbeat sampling was
needed, its original source instrument and observation time.

The GitHub continuous observer logs a limited engine stderr on
nonzero exit. Verified all-provider failures skip the corresponding
ten-minute slot and retry only at a later real wall-clock time, with
three-consecutive-outage circuit breaker. Other exceptions and ledger
integrity failures still terminate immediately. No stale quote can be
relabelled as a successful observation; missed slots remain missed.


## Automated independent quality re-audit and venue provenance (2026-10-15)

The read-only quality-gate workflow is scheduled twice daily and runs
after successful historical Research Factory completion in addition to
PR/explicit triggers. It uses contents-read permissions, checks all
canonical ledger events, pairs frozen-stratum controls, tests strict
research quality gates, and retains a source-hash-linked downloadable
report for 30 days. No forward trading or automatic strategy promotion.

Each actual-time primary report includes `live_source_quality` with
validated perp vs spot snapshots, real active venue names and failed
attempted source pairs. A fully spot-only tick stays observable but
cannot masquerade as perpetual trade evidence. Venue health diagnostics
never create an OPEN/CLOSE or modify the hash-chained original events.


### Operating cadence recovery buffer
The guardian keeps requesting a single safe workflow-run handoff when
the 72-observation-slot measured coverage is below 95% rather than
stopping immediately at 90%. It refuses parallel or queued successors,
stale reports and unverifiable completion receipts. Recent-12 and
recent-36 observed-gap coverage are shown separately from the unchanged
strict last-72 headline number to make actual recovery visible while
historical missed slots roll off naturally. Scheduled GitHub runners
remain best effort and can consume substantial monthly CI minutes.


### 750-family research catalogue expansion
V9.3 factory covers 750 parameter settings with versioned deterministic
families and preserved original 500 experiment IDs. CI verifies the
complete count and family provenance against the published report;
historical promotion remains blocked without independent, future-only
prospective validation. Historical re-runs cost more compute; no v8
trade history is rewritten or traded live.
