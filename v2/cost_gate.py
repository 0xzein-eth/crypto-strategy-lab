"""Compute true quoted spread + assumed cost breakeven for forward SHADOW hypotheses.

No predictive model ships with this module. A positive quote-only forecast
is not a validated model, and NOTHING here opens a v8/v2 trade. The
result is research observability only; costs are explicitly hypothetical.
"""
from decimal import Decimal
from v2.paper_portfolio import D, verify_quote, OrderRejected

VERSION = "v2-cost-viability-shadow-only-1"


def break_even(quote, now, symbol, side, *, taker_fee_rate="0.0005",
               assumed_funding_adverse_bps=8, impact_latency_bps=10,
               safety_buffer_bps=10):
    """Favorable MID-price percentage needed for nonnegative theoretical edge.

    Long enters at current ASK and projects later executable BID; short
    enters BID and projects exit ASK. Assume same proportional quoted spread
    on future exit. Futures actual spread and slippage may be *worse*.
    """
    if side not in ("LONG", "SHORT"):
        raise OrderRejected("ORDER_INVALID: buy/sell side")
    book = verify_quote(quote, symbol=symbol, now=now)
    fee = D(taker_fee_rate)
    funding = D(assumed_funding_adverse_bps)
    impact = D(impact_latency_bps)
    safety = D(safety_buffer_bps)
    if (fee < 0 or fee >= Decimal("0.01") or
            any(x<0 or x>200 for x in (funding,impact,safety))):
        raise OrderRejected("COST_INVALID: unsafe fee/funding/stress assumptions")
    mid = (book["bid"]+book["ask"])/2
    adverse_pct = (funding+impact+safety)/Decimal(10_000)
    if side == "LONG":
        buy = book["ask"]
        exit_quote_per_mid = book["bid"]/mid
        threshold_future_mid = buy*(1+fee+adverse_pct)/(exit_quote_per_mid*(1-fee))
        favorable = (threshold_future_mid/mid-1)*100
    else:
        sell = book["bid"]
        exit_quote_per_mid = book["ask"]/mid
        threshold_future_mid = sell*(1-fee-adverse_pct)/(exit_quote_per_mid*(1+fee))
        favorable = (1-threshold_future_mid/mid)*100
    return {
        "version": VERSION, "symbol": symbol, "side": side,
        "observed_quote_timestamp": book["observed_at"],
        "observed_bid_usdt": str(book["bid"]),
        "observed_ask_usdt": str(book["ask"]),
        "quoted_spread_bps": float((book["ask"]-book["bid"])/mid*10000),
        "roundtrip_taker_fee_bps_reference": str(fee*20000),
        "assumed_adverse_funding_bps": str(funding),
        "assumed_extra_impact_latency_bps": str(impact),
        "precommitted_buffer_bps": str(safety),
        "minimum_favorable_mid_move_pct": float(favorable),
        "predicted_move_is_not_available": True,
        "actual_future_execution_is_unknown": True,
        "trading_authorized": False,
    }


def shadow_decision(quote, now, symbol, side, *, forecast_favorable_move_pct=None,
                    forecast_model_id=None, model_training_end=None, **costs):
    """Cost-hurdle *visibility* gate; never places or promotes any trade.

    Uncalibrated forecasts are NOT alpha proof, even when exceeding hurdle.
    To avoid choosing signals from future training, reject unversioned and
    future-trained forecasts; callers MUST pass an authentic training record.
    """
    burden = break_even(quote, now, symbol, side, **costs)
    status = "NO_FROZEN_OUT_OF_SAMPLE_FORECAST"
    reason = "No verified frozen model forecast exists. Abstain."
    if forecast_favorable_move_pct is not None:
        from v2.paper_portfolio import ts
        import datetime as dt
        end = ts(model_training_end) if model_training_end is not None else None
        if (not isinstance(forecast_model_id,str) or not forecast_model_id or
                end is None or end >= ts(now)):
            status = "MODEL_PROVENANCE_INSUFFICIENT"
            reason = "Forecast missing version or trained with future/current observation."
        else:
            v = D(forecast_favorable_move_pct)
            if v < 0 or v>20:
                raise OrderRejected("FORECAST_INVALID: implausible unsigned move")
            if v <= D(burden["minimum_favorable_mid_move_pct"]):
                status = "FORECAST_BELOW_AFTER_COST_HURDLE"
                reason = "Hypothetical forecast fails fee, spread, funding and latency buffer."
            else:
                status = "EXPLORATORY_SHADOW_CANDIDATE_ONLY"
                reason = "Forecast exceeds theoretical hurdle but is NOT an independently validated alpha or executable fill."
    return {**burden, "status":status,"reason":reason,
            "not_for_live_orders":True,
            "auto_paper_portfolio_entry":False,
            "champion_proven":False}


