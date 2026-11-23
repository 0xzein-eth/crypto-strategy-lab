"""Pre-registered hypothetical execution-friction STRESS scenario, never fills.

The actual lab close remains fixed-horizon last-trade-to-last-trade less fees.
This additional scenario uses OBSERVED entry spread when supplied and explicitly
estimated market impact; it is not an execution model or guaranteed slippage.
"""
import math
import universe

VERSION="friction-scenario-v1"
MAJOR={"BTC","ETH","SOL","BNB"}
MAX_ROUND_TRIP_EXTRA_PCT=0.50


def observed_spread_pct(bid,ask):
    """Percentage bid/ask width. None if no authenticated market quote exists."""
    try:
        b,a=float(bid),float(ask)
        if not all(math.isfinite(x) and x>0 for x in (a,b)) or a<b:
            return None
        result=100*(a-b)/((a+b)/2)
        return round(result,8) if result<=5 else None
    except (TypeError,ValueError,ZeroDivisionError):
        return None


def estimate_extra_round_trip_pct(symbol, change24h_pct, quote_volume, spread_pct=None):
    """Scenario: two spreads/impact legs estimated from observable opening inputs.

    Spread crossing ~ one full bid/ask spread for round trip. Market impact is an
    assumed per-side buffer; notional vs 24h volume cannot prove actual fills.
    """
    turnover=float(quote_volume)
    change=float(change24h_pct)
    if not math.isfinite(turnover) or turnover <= 0 or not math.isfinite(change):
        raise ValueError("invalid source volume/momentum for friction scenario")
    if spread_pct is None:
        assumed_spread = 0.025 if symbol in MAJOR else (
            0.06 if universe.sector(symbol)=="meme" else 0.045)
        spread_basis="assumed"
    else:
        assumed_spread=float(spread_pct)
        if not math.isfinite(assumed_spread) or assumed_spread<0 or assumed_spread>5:
            raise ValueError("invalid bid-ask spread")
        spread_basis="observed_entry"
    base_impact = 0.008 if symbol in MAJOR else (
        0.04 if universe.sector(symbol)=="meme" else 0.025)
    liquidity_buffer=min(0.065, 0.005*math.sqrt(50_000_000/turnover))
    volatility_buffer=min(0.065, abs(change)*0.002)
    # One spread across entry+exit, two impact buffers, rounded UP in stress.
    extra=min(MAX_ROUND_TRIP_EXTRA_PCT,
              assumed_spread + 2*(base_impact+liquidity_buffer+volatility_buffer))
    return {
        "version":VERSION,
        "assumed_round_trip_extra_pct":round(extra,6),
        "source_spread_pct":round(assumed_spread,8),
        "spread_basis":spread_basis,
        "description":"hypothetical crossing and impact stress, NOT a real fill",
    }


def scenario(signed_return_pct, notional_usd, research_risk_pct, extra_pct):
    extra_pct=float(extra_pct)
    fees_pct=0.10
    if extra_pct<0 or extra_pct>MAX_ROUND_TRIP_EXTRA_PCT:
        raise ValueError("invalid frozen friction parameter")
    stress_pnl=notional_usd*(signed_return_pct-fees_pct-extra_pct)/100
    stress_R=(signed_return_pct-fees_pct-extra_pct)/research_risk_pct
    return {"stress_net_pnl_usd":round(stress_pnl,6),
            "stress_normalized_R":round(stress_R,8),
            "stress_extra_cost_usd":round(notional_usd*extra_pct/100,6)}

# Illustrative post-only maker-fee counterfactual. This is NOT evidence that
# an order would have filled; queue position, adverse selection, partial fills,
# cancellations and venue/account fee tiers are not modeled.
MAKER_FEE_SIDE_PCT = 0.01


def maker_counterfactual(signed_return_pct, notional_usd, research_risk_pct):
    """Reprice a fixed-horizon outcome at an illustrative maker fee only.

    Keep this diagnostic separate from the primary taker/stress result. It
    assumes both legs fill as maker at 0.01% per side and does not model fill
    probability, spread capture, queue priority, rebates or adverse selection.
    """
    values = (signed_return_pct, notional_usd, research_risk_pct)
    try:
        ret, notional, risk = (float(v) for v in values)
    except (TypeError, ValueError):
        raise ValueError("invalid maker counterfactual input")
    if (not all(math.isfinite(v) for v in (ret, notional, risk)) or
            notional <= 0 or risk <= 0):
        raise ValueError("invalid maker counterfactual input")
    fee_round_trip_pct = 2 * MAKER_FEE_SIDE_PCT
    fee_usd = notional * fee_round_trip_pct / 100
    net_pnl = notional * (ret - fee_round_trip_pct) / 100
    return {
        "maker_fee_side_pct": MAKER_FEE_SIDE_PCT,
        "maker_fee_round_trip_pct": fee_round_trip_pct,
        "maker_fee_round_trip_usd": round(fee_usd, 6),
        "maker_net_pnl_usd": round(net_pnl, 6),
        "maker_normalized_R": round((ret - fee_round_trip_pct) / risk, 8),
        "maker_fill_assumed_not_verified": True,
        "description": "illustrative maker-fee counterfactual only; not an executable-fill estimate",
    }
