# Crypto Strategy Lab v9 — Historical Research Factory

## Operational separation

Version 8 remains the immutable-source-of-truth *prospective* paper lab.
Version 9 is a **separate historical backtesting research lane**. Neither its
candles nor its simulated entries/exits are ever appended to data/events/,
data/state.json, data/report.json, or legacy data/ledger.json. It cannot place
real orders and requires no private exchange credentials.

Version 9 adds:

- Public OKX USDT swap 15-minute confirmed OHLCV history with bounded paging,
  exact derivative instrument identity, no silent gaps, and strict cross-run
  overlap checks. Compressed symbol-specific caches are capped at 6,000 bars.
- A deterministic, predeclared factory of up to 250 parameterized variants
  across trend, momentum, mean-reversion, breakout, RSI, plus long and
  deterministic directional controls. Example production setting: 250.
- Fixed-horizon 1, 2, 4, 8, 24-hour **historical** simulation. Signal at the
  most recently finished 15-minute candle, hypothetical entry at NEXT candle
  OPEN, hypothetical exit at the future candle OPEN, no SL/TP.
- Assumed trading cost of 0.05% per side, plus separate 0.12% hypothetical
  spread/impact haircut. Funding, liquidation, orders, actual bid/ask fills,
  leverage and execution latency are **not fully modeled**.
- Chronologically expanding training with 96-bar purge/embargo before each
  of three subsequent validation windows. Training alone chooses candidates
  in each fold; validation never influences selection *within the same fold*.
  The validation windows are repeatedly inspected on future runs, so this
  method does NOT deliver a pristine final holdout.
- Day-grouped descriptive lower bounds rather than miscounting hundreds of
  correlated trades as independently verified evidence.
- Daily scheduled GitHub Action plus manual trigger, regression tests, fail-
  closed provider handling, and isolated Git history commits for research
  cache/report only.

## Execution

CI: \`python -m unittest discover -s tests -p 'test_research_v9.py' -v\`

Daily (network): \`python run_research_v9.py --symbols BTC ETH SOL LINK XRP ADA AVAX DOGE --cold-pages 16 --update-pages 10 --max-variants 260\`

Offline (requires already-populated cache): \`python run_research_v9.py --symbols BTC ETH SOL LINK XRP ADA AVAX DOGE --offline --max-variants 260\`

Workflow: \`.github/workflows/research.yml\`. Scheduled 03:19 UTC daily
(10:19 WIB), with GitHub Actions best-effort delivery. Public endpoints may
block GitHub IPs; status should FAIL when less than two usable instruments are
available. No fabricated prices, interpolated candles, or retroactive paper
fills are permitted. Eight requested instruments can be degraded to two while
explicitly listing errors. Fresh confirmed candle staleness cannot exceed 3h.

For prospectively observed strategies and valid OPEN/CLOSE records, continue
using \`.github/workflows/lab.yml\` and the v8 paper ledger. The historical
factory does not automatically change v8 live-paper policies.

## Files

| Path | Meaning |
|---|---|
| \`research_v9/history.py\` | OKX history ingestion, price quality & cache integrity |
| \`research_v9/factory.py\` | Predeclared variant grid, signals and chronological evaluation |
| \`run_research_v9.py\` | CLI and reproducible data provenance |
| \`research_cache/okx_swap_15m/*.json.gz\` | Compressed capped historical dataset; never v8 event data |
| \`research_results/latest.json\` | Historical outcomes, caveats, validation folds and source digests |
| \`tests/test_research_v9.py\` | Independent offline regression/anti-leakage tests |
| \`.github/workflows/research.yml\` | Scheduled validation and publishing |

## Interpretation and next research stages

A factory-generated winning curve is **not** proof of edge, and historical
backtests are not actual fills. Every scored strategy is vulnerable to
multiple-testing bias, hidden regimes, and missing execution frictions.
Fields \`proven_edge=false\` and \`champion=null\` are intentional. Promotion
to additional v8 prospective paper experiments requires a separate versioned
strategy bridge that preserves v8 auditable signal evidence; it is not
silently enabled by this change.

Suggested next stages: additional independent venues, funding-rate snapshots,
contract-specific bid/ask cost modeling, global-date anchored walk-forward
comparison, and explicit promotion-gated forward paper candidates.
