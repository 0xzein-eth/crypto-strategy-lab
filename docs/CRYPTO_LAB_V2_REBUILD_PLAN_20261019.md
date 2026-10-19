# Crypto Strategy Lab v2 — Evidence-First Rebuild Plan
**Created 2026-10-19 | Research/architecture only | PAPER-ONLY existing project unchanged**

## Executive decision

**STOP scaling the existing trade count as an objective.** The v8 experiment ledger is useful as an immutable record of real observed *quotes* and simulated outcomes, but it is not evidence that its cumulative paper P&L represents a fundable portfolio, that the signals have positive post-cost alpha, or that the v9 historical factory is a deployable strategy. Keep the v8 code and original ledger as **legacy research**. Create a separate, future-versioned, **no-orders research platform** whose first tasks are (a) sufficiently long true market data, (b) realistic net execution and portfolio accounting, (c) shared backtest/live signal implementation, (d) independent statistical selection, and (e) persistent, reliable observation. Do not launch real futures trades by default.

The user wants a high win rate. **Win rate is a conditional statistic, not a return target:** expected net edge = P(win) × average win – P(loss) × average loss – costs. Strategies may have high WR and still bankrupt an account. Positive post-cost, risk-adjusted out-of-sample expectancy and controlled drawdown must be the primary acceptance gate. A 55–65% WR could be an *aspiration to investigate*, never a guarantee or a required selection target.

## Baseline audit: supported by current repository source, not conjecture

Canonical snapshot: `data/report.json` on 2026-10-19 09:26:49 UTC, before any future v2 experiment.

| Fact | Audited number | What it means |
| --- | ---: | --- |
| CLOSED paper positions | 12,231 | correlated research events, **not** 12,231 independent trials |
| Created/OPEN | 12,746 / 515 | many positions overlap across assets/horizons |
| Actual paper net fee-only P&L | −$117,333.40 | sum of hypothetical $10,000 per-position notionals, not funded account profit |
| Explicit `total_round_trip_fees_usd` | $122,310.00 | 0.05% *each side* × 2 × $10,000 × CLOSED |
| Implied gross direction-only P&L | +$4,976.60 | after adding the modeled fee back; $0.407 gross per close |
| Gross edge averaged per position | +0.00407% | **far below** 0.10% roundtrip fees, without spread/impact |
| Win rate / profit factor | 46.46% / 0.8907 | negative expectancy |
| Timely eligible perpetual outcomes | 10,680 | historical late and spot proxy events are not valid perp edge labels |
| Late CLOSED | 1,551 | cannot be retroactively rebadged as timely research |
| Rolling 10-min observation coverage | 85.37% | recent 12 gaps 100%, but 117.8-minute gap still in 72-interval window |
| v9 historical research | 2,000 variants / ~6.21m simulated trades / 12 coins | repeated, correlated parameter searches, not independent signals |
| v9 common search period | 2026-07-21 → 2026-10-19 (~90 days) | inadequate for robust multi-regime generalization |
| v9 walk-forward | 3 folds, only middle fold 10 train-qualified, 4 validation-selected | all four selected middle-fold validation mean R values negative |
| v9 status | no proven edge, no champion | existing statistical gate appropriately refuses promotion |
| v8 calendar evidence | 12 UTC entry days, 3 ISO weeks | not sufficient for reproducible, multi-regime evidence |
| Example forward strategies | FB-v3 n161 +0.1898 after-stress R, VWAP-v1 n207 +0.1248 after-stress R | candidates for *independent* follow-up only, not proven; no matched-control claim |
| Strong negative cohorts | BR-proxy-v1 2,751 timely -0.1817 after-stress R; RSITREND-v1 388 timely -0.5401 R | large experimental effort spent on negative hypotheses |

`engine.py` hardcodes `NOTIONAL_USD=10000` for **every OPEN**, permits `MAX_OPEN=1050`, and sets `hypothetical_leverage=3`. At max capacity that implies $10.5m concurrent nominal exposure and ~$3.5m nominal 3× initial margin **before maintenance, correlation and liquidation constraints**. There is NO equivalent capital/equity account ensuring an individual account could fund the overlapping positions. Hence the huge negative dollar sum is NOT an account equity curve; raw number of positions and dollar P&L must not be the lab's central achievement.

Other identified gaps:
- `engine.close_due` prices simulated OPEN/CLOSE with snapshots and static fees; `funding_assumption_usd=0`; observed entry spread and extra adverse impact are a separate *hypothetical stress*, **not** an exchange fill. No realistic order rejection, partial fill, fee tier, funding cash ledger, liquidation or portfolio buying power.
- Historical `research_v9.factory.backtest` enters at a **next confirmed bar open**, while live paper enters at a later **fresh ticker snapshot**. These are different implementations/time alignments. Historical backtests can screen hypotheses; they cannot validate v8 implementation on their own.
- v9 uses a common **90-day** window for funding completeness, even though raw OHLCV caches span more; independent regimes and multiple years are not covered. It uses three **repeatedly observed** purged chronological folds (96 × 15m embargo, ~24h); none is a *new, untouched final holdout*. Four historical middle-fold finalists all had negative validation mean R.
- Strategy proliferation (2000 parameter variants, ~6.2m correlated hypothetical backtest rows) drastically increases selection/multiple-comparisons risk; adding even more variants is counterproductive without a locked testing budget and adjustment.
- `scheduler_guard`, `recovery_window` and GitHub Actions best-effort clocks cannot guarantee timely 10-minute or shorter execution. Recent continuous-handoff fixes mitigate gaps, but uptime improvement needs *future evidence*, not a passed unit test.
- The v8 `learner-v8` sparse-proxy/throttled-loss policy changes *how often/which* experiments are sampled. A lower negative total after a change must **never** be called higher edge without conditional performance and matched controls. Monitor data have repeatedly been inspected.

## Implementasi awal P1/P2: data integrity & signal parity

- `v2.data_contract` produces SHA256 per exact OKX instrument series,
  truthful UTC/15m/contiguous window length and separately NULL/UNKNOWN
  settled funding coverage; it rejects duplicate/missing/invalid
  historical bars rather than filling them. A read-only daily Actions
  artifact documents the current cached data; it does not extend
  history beyond authentic upstream observations.
- `v2.signal_parity` uses deployed `signals.classify` both on
  **as-of** replayed cached candles and a reconstructed public OKX
  `signals.from_okx` adapter. Future/unfinished candles are excluded
  and exact frozen signal fingerprints are compared. This validates
  parsing/feature parity for **currently deployed 15m hypotheses**,
  *not* the separate v9 2,000-parameter factory or historical next-bar
  fill simulation.
- `proposed_entry_drift` makes next-open vs later ticker price/time
  divergence inspectable, never treating either as real executed fill.
- All tests are synthetic deterministic regressions. >=365 days of
  authentic market history and real bid/ask/funding completeness are
  still blocked on data acquisition and are NOT claimed delivered.

## Non-negotiable design principles

1. **Three physically/logically separated modes:** historical hypothesis exploration, immutable prospective *shadow signal* observation, and realistic simulated portfolio execution. A fourth optional real-broker adapter does **not exist** until reviewed and explicitly approved.
2. **One source implementation for features & signals**, same contract across historical / replay / forward; market price observation and simulated fill accounting differ by environment but have a formal reconciliation test. Freeze signal ID, hash, parameters, data cursor, venue, clock, horizon, filter decision and policy version at proposed entry time.
3. **No-trade is a valid, necessary output.** Count signal opportunities, veto reason and qualified entries rather than inflate trade volume. Control comparators are deliberate, sparse, prospective and matched *before* allocating future prices.
4. **Model the actual account**: wallet equity, locked margin, maintenance threshold, funding ledger, maker/taker fee, observed bid/ask, order type, liquidity, exposure concentration, failed/partial fills and liquidation risk. A 3× *parameter* is not a simulated liquidation engine.
5. **Real costs are primary, sensitivity secondary.** Report price-only gross, fee-adjusted, bid/ask/slippage, funding-adjusted, stressed funding/impact *separately*; never relabel assumptions as measured fills.
6. **Two honest success criteria:** (a) accurate, reliable research, even if it finds no profitable strategies; (b) independent demonstrable net edge, if one actually exists. Passing (a) does not prove (b).
7. No historical ledger rewrite; no automatic real trades; existing fixed 1/2/4/8/12/24-hour v8 paper positions do not acquire stop/TP/trailing exits retroactively. Novel exit policies, if ever explored, belong to a separately approved prospective version.

## v2 target architecture

```text
OKX public REST/WS (15m OHLCV, historical candles, book bid/ask/depth,
                   trades, mark/index, settled funding, open interest)
           |
           v
[data_ingest] --> raw immutable UTC timestamped snapshots + provenance
           |    schema/duplicates/gaps/revisions/rate-limit QA, checksums
           v
[feature_engine] --> strictly as-of features shared by backtest and forward
           |
           +--> [strategy_registry] frozen thesis, vetoes, unique version, regimes
           |            |
           |            +--> [research_sim] walk-forward + realistic costs/account
           |            |         --> [stats_gate] candidate + controls + uncertainty
           |            +--> [shadow_observer] all eligible SIGNALS + abstentions
           |            |         --> independent forward scorecards, no-orders
           |            +--> [portfolio_paper_sim] wallet, orders, fees, funding,
           |                      latency, partial fills, margin and liquidation
           |                      --> comparable net equity curve
           |
           v
[reports] reproducible, stratified, cohort-ID/version-aware dashboards
[CI] invariant, leak, funding, fill, data, no-order & audit tests
[operations] nightly GH Actions ETL/research; precise observer only with
             separately reliable service, otherwise reduced cadence
```

### Workstream A — market data first

- Build 1–3 **years** of *usable* supported derivative instrument OHLCV, with 15m plus 1m where reliably supported and synchronized; aim to span different BTC regimes (trend/range/crashes/low/high volatility) and exchange market structure. **Do not claim historical years unavailable from upstream APIs are covered.** Account for delisted survivors rather than only today's 12 surviving markets.
- Keep the *price-only longer-window* experiment alongside an explicitly *funding-complete shorter-window* subset; if historical settled funding is missing, label/mask, NEVER fill with zero or assume known funding.
- Capture bid/ask, depth and trades for **future** observations (and historical if licensed/retrievable); record source, exchange, instrument, receive UTC, exchange UTC, price age, market type, missingness, tick size, lot size and version. Separate mark/index/last-trade prices.
- Require event-time monotonicity, no future features, no duplicate bar boundaries, no speculative gapfill, exact market/contract, funding settlement intervals, explicit delisting/missing symbols. Introduce content-addressed compressed columnar dataset/artifacts; avoid committing millions of raw ticks to `main`.
- Acceptance: reproducible checksums & manifests; >=99.5% **verified in-scope bars** contiguous where a historical window is declared complete; missing periods audited; >=365 days first milestone, >=730 days preferred; independent feed reconciliation at sampled timestamps. Percentages are planning thresholds, not achieved numbers.

### Workstream B — reproducible research / fair reference

- First construct **no-skill references**: no-trade, frozen random long/short, 24h direction proxies, market beta long-only, time-shuffled, and exactly matched controls. Group matched by asset, venue, side, UTC day, regime and horizon; publish fraction matched.
- Use one vectorized candidate generation path for speed and an **event-driven** test mode for fill, fees, funding, simulated wallet and order constraints. Fit no model/threshold using future values; `asof(signal_time)` contract mandatory. Compare historical predicted candidates to live shadow candidates on overlapping real periods and explain differences.
- Add feature ablation and cost feasibility: if expected move does not cover roundtrip fees/spread/funding/impact plus safety margin, the entry is **vetoed** prospectively. Minimum expected edge thresholds must be selected using training only, versioned and sensitivity-tested; a predictor output is not a realized price expectation.
- Acceptance: identical signal/side for frozen completed historical vs replayed as-of candle; no lookahead, no recursive indicator instability, no unrealistically perfect fills; symbol/day/horizon controls frozen before the result.

### Workstream C — smaller, stronger candidate hypotheses

Freeze a **research budget of about 4–6 genuinely distinct families**, not thousands of almost-identical threshold variants:
- **Trend continuation / pullback**: multi-timeframe 1h/4h bias with 15m setup, minimum net movement vs cost; volume/volatility context.
- **Failed breakout / sweep reversal**: range break plus confirmed rejection/absorption with spread/liquidity check, not automatically every RSI extreme.
- **Volatility squeeze → confirmed expansion**: pre-break compression, post-break follow-through, avoid high-impact gap/noisy thin markets.
- **Range mean reversion**: only in objectively rangebound + liquid regimes; cost-aware exit target horizon.
- **Funding and basis / crowding context**: include funding/OI as causal *features* only if truly measured before signal; do not equate high funding with guaranteed reversion.
- **Meta-filter of opportunities**, only after reliable labels: calibrated `P(win | true confirmed signal, regime, cost)` plus predicted win/loss *size*, trained with date-grouped purged evaluation. High P(win) alone cannot override negative net expectancy.

Evaluate separate LONG/SHORT, symbol, horizon and regime. Set no-trade region and abstention as the default, and stop **creating new versions** while one independent preregistered assessment is underway. Keep a shadow reference for rejected versions, but **no unadjusted leaderboard**.

### Workstream D — trustworthy out-of-sample strategy selection

- History: expanding/rolling train with at least **2 years where available**, disjoint chronological walk-forward tests over non-overlapping future months; purge any training labels overlapping test horizons and embargo documented feature/holding windows. Existing 90-day folds remain an *exploratory baseline*, not deployment evidence.
- Selection: predeclare variants, outcome metric, number of tested configurations (including rejected), training windows, control matching and strategy-version-specific embargo; apply multiple-hypothesis corrections (Holm / Deflated Sharpe / PBO where meaningful). Test by UTC **day/week and regime blocks**, not treating simultaneous altcoin trades as i.i.d.
- Choose only strategies with positive **after-fees, bid/ask/funding-adjusted** net expectancy; conservative stress scenario; robust costs; controlled concentration; enough signals *without optimizing on a repeatedly viewed validation period*.
- After any tuning/ranking freeze a completely **new untouched chronological forward holdout** (e.g. 60–90 days, spanning multiple weeks/regimes; may need longer). Do not reselect while that final window runs; a failed result triggers a NEW experiment with a NEW future holdout, not tweaking the same one.
- Acceptance gate proposal, all simultaneously (NOT guaranteed or by itself proof of live profitability): >=8 distinct observed ISO weeks or 60–90 genuine forward calendar days,>=40 independent entry-day groups when applicable, enough matched genuine controls with prespecified power/match fraction, after-cost **net R lower confidence bound >0** under independent final validation after multiple-testing correction, stress scenario >0, profit factor >=1.20 after validated cost assumptions, drawdown within an explicitly modeled bankroll budget, no single symbol/day accounting for a dominant fraction. Confidence thresholds and power plans must be frozen before evaluating final test. **Win rate displayed**, not mandatory 60% selection gate.

### Workstream E — portfolio simulator and real-execution plausibility

- Introduce a *single hypothetical wallet* (e.g. 1,000 USDT test capital, purely configurable), risk and exposure limits, equity, realized/unrealized P&L, maintenance margin, fees, funding, currency, order execution timestamps, risk concentration and deterministic liquidation scenario. Notional cannot be booked if insufficient free collateral.
- Simulated entry/exit order modeling: for BUY use observed ASK (or conservative executable book depth) and SELL use BID; estimated slippage/impact by traded size, queue and volatility; partial/non-fill and missing quote outcomes. Differentiate measured market-data fields from hypothetical impact/latency.
- Report two distinct ledgers: immutable v8 **research-event notional scorecard**, and v2 **cash-constrained hypothetical portfolio**. Never infer v2 results from simply summing v8 $10k positions.
- Paper portfolio starts with **no live API credentials**; after independent performance proof and only by user approval, optional sandbox connector with exchange's actual testnet fills may be developed. Real orders, leverage and any change from the predeclared fixed exit policy require separate explicit authorization.
- Acceptance: equity always reconciles to positions/cash/fees/funding; insufficient margin blocks new entry; liquidation logic tested; max modeled drawdown/risk limits verified; never implicitly trade a real account.

### Workstream F — reliability, economics, transparency

- GitHub Actions: use for CI, **scheduled batch history fetch**, research runs and report publishing. Best-effort GitHub cron can be delayed/dropped; no firm 10-minute quote-clock or tick-to-order guarantee.
- For **10-minute (or shorter) reliable shadow/paper timing**, use independent always-on observer/managed worker with durable queue/heartbeat and appropriate budget, with storage external to Git as needed. If user requires **free GitHub-only**, accept lower cadence and restrict studies to longer horizons where end timestamp observation tolerance is appropriately predeclared; do not game late exclusions.
- Track measurement explicitly: *genuine* observation coverage, max gap, source health, stale price, missed expected deadline, late-excluded closes, rejected orders, cost-to-run (Actions minutes / storage), dispatch duplicate / conflict rates.
- Daily dashboard separated into **data quality / hypothesis opportunity / paper portfolio net metrics / selected final forward validation**. Show research experiments, sample size, negative results and "not enough evidence"; never show only highest win rate.
- Acceptance: >=99% in-scope **fresh shadow observations** over a continuous 30-day prospective window *only if a suitable observer exists*, no synthetic gapfills or out-of-order ledger events, no credentials in Git or CI logs; fail closed when status cannot be verified.

## Concrete phased build plan, prerequisites and definition of done

| Phase | Suggested effort* | Owner artifact / implementation | Exit condition |
| --- | --- | --- | --- |
| **P0: freeze / diagnose** | 2–4 working days | audit fee attribution; cost sources; source alignment; per-policy-version cohorts; current P&L exposure disclaimer | Existing immutable v8 ledger locked; executable accounting gap and selection risk documented; zero live orders |
| **P1: Market Data v2** | 1–3 weeks plus backfill fetch time | `v2/data_contract.py`, immutable dataset manifests, OHLCV/funding/book adapters, missingness QA | >=1 year truthful verified multi-regime candles across chosen markets or documented blockers; exact-venue provenance |
| **P2: Signal/backtest parity** | 1–3 weeks | `v2/strategies/`, common as-of feature engine, backtest/replay parity tests, no lookahead/recursive checks | All comparison fixtures pass; next-bar and current-quote selection difference quantified |
| **P3: Realism + wallet** | 2–4 weeks | `v2/execution/`, `v2/portfolio/`, fee/funding/impact/partial fill/margin accounting | Unit ledger balances reconcile; nonexistent cash/order fill prohibited; stress test does not masquerade as observed |
| **P4: Economic discovery** | 2–4 weeks initially | 4–6 preregistered thesis families, leave-one-asset-out, rolling/purged backtests, independent controls & multiplicity docs | Candidates either have positive net training results robust to sensitivity or honestly marked `NO_EDGE` |
| **P5: Untouched forward trial** | **>=60–90 calendar days** | version-frozen `v2/shadow/` + v2 paper wallet, heartbeat, cohort selection manifest, day-cluster reports | independent final gates passed; otherwise stay paper-only / hypothesis rejected |
| **P6: Deployment review** | Only if P5 passes | operations/security/order adapters **proposal**; testnet first, separate explicit user approval required | No real orders without explicit separate approval; measured execution deltas, risk limits and budget documented |

*Indicative planning ranges, not background job commitments or guaranteed completion dates. Work phases overlap only if that cannot leak outcome information. The 60–90-day test cannot be accelerated by running 100× correlated trades.

## Implementation priorities for the NEXT engineering PRs

| Order | Proposed issue | Exact test(s) / deliverable |
| --- | --- | --- |
| 1 | Separate fee gross/net and legacy research notional from investable equity | regression using current canonical report: 12,231 × $10 fee = $122,310; mandatory fee/markout/gross dashboard with cohort version |
| 2 | Historical/forward signal parity harness | same frozen confirmed candles → same side, signal and input hash; no lookahead and cold-start recursive checks |
| 3 | Longer validated prices + truthful funding missingness | per-market completeness and multi-regime data provenance manifests; no fill-with-zero |
| 4 | Realistic event-driven hypothetical wallet | balance identity, bid/ask fee funding scenarios, rejected fills and liquidation fixtures |
| 5 | Distinct strategy proposal register and cost-aware veto | 4–6 theses, precommitted hypothesis IDs and training-only choice; show abstention and signal-veto reasons |
| 6 | Proper clean final testing | original train/validation/final boundaries, embargo and multiple trial accounting, matched controls and independent days |
| 7 | Reliable shadow observer | uptime measured from independently stored *real market timestamps*, outage states and clock costs |

## Practical platform comparison

| Reference platform | Adopt | Do not assume |
| --- | --- | --- |
| Freqtrade (open source) | `lookahead-analysis`, `recursive-analysis`, dry-run/backtest parity practices | Its example ROI/stop/TP logic is NOT the existing v8 exit contract; dry-run fills can differ from live |
| QuantConnect LEAN (open source) | distinct brokerage/portfolio/order/fee/slippage/fill/margin model boundaries | Market models do not magically provide accurate crypto order book data or guaranteed fills |
| Existing Python + GitHub | transparent append-only event ledger, tests, historical experiment catalog and versioned signals | GitHub cron is NOT a precision real-time observer or portfolio simulator by itself |

## Explicit "do not do"

- No **90% win-rate guarantees**, auto-optimization to maximize observed WR, invented fills, no-fee backtests, or claiming +$ after disabling losing trades.
- No doubling trade count, thousands more correlated parameter variants, or code editing during an untouched forward trial.
- No using 2,000 already inspected variants as 2,000 independent validations or 12 observed entry days as evidence across a 4-year bull/bear cycle.
- No deploying leverage with borrowed/personal cash, no open futures API secrets in GitHub, and no move from paper research to actual orders without a separate, deliberate decision.

## Sources and engineering precedents

- Bailey & López de Prado, *The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality*, J. Portfolio Management (2014): https://doi.org/10.3905/jpm.2014.40.5.094
- Bailey, Borwein, López de Prado & Zhu, *The Probability of Backtest Overfitting*: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- Freqtrade, *lookahead-analysis*: https://www.freqtrade.io/en/stable/lookahead-analysis/
- Freqtrade, *recursive-analysis*: https://docs.freqtrade.io/en/stable/recursive-analysis/
- Freqtrade, *Strategy Quickstart* (backtest/dry-run divergence): https://www.freqtrade.io/en/stable/strategy-101/
- QuantConnect LEAN, *reality modeling*: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts
- QuantConnect LEAN, *slippage*: https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/supported-models
- QuantConnect LEAN, *reconciliation*: https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/reconciliation
- GitHub Docs, *Troubleshooting scheduled workflows*: https://docs.github.com/en/actions/how-tos/troubleshoot-workflows
- Official OKX API (market/derivative/funding endpoints): https://www.okx.com/docs-v5/en/
