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
2. The default GitHub Actions paper tick is at minutes `:03, :13, :23,
   :33, :43, :53` each UTC hour (six target opportunities per hour).
   GitHub does **not guarantee** punctual execution or delivery.
3. At each successful market run, record `scheduling_diagnostics` in the
   *derived report*. `prior_observation_gap_minutes` is measured from the
   last successfully committed market report. It is not the actual time
   the cron was intended to fire.
4. After a gap >45 minutes, **new entries are throttled to at most two**
   per recovery run, while all due exits are still attempted. The next
   on-time run resumes normal selection automatically. This rule only
   affects future experiments; all old OPEN/CLOSE entries and their hashes
   are preserved.
5. A separate GitHub Actions watchdog targets minutes `:09` and `:39`
   each hour and fails when the last verified report is >75 minutes old.
   A failed watchdog can surface GitHub notifications, but it cannot
   detect an outage if GitHub does not start the watchdog either.
6. Run the full regression suite on CI pushes and PRs. Paper ticks run
   a targeted set of offline lifecycle tests plus full ledger audit;
   this avoids repeatedly running heavy historical research tests.

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
