"""Pre-registered research-only strategy combiners.

Input signals are contemporaneous and generated elsewhere from completed
candles. No price features, forward data, execution or live orders here.
Distinct composite hypotheses MUST be validated chronologically out of sample.
"""
from collections import Counter

COMPOSITES = {
    "consensus_trend_breakout_v1": ("TREND-v1", "BR-v3", "DC-v1"),
    "consensus_reversion_v1": ("MR-v3", "RSI-v1", "BANDREV-v1"),
    "consensus_volume_momentum_v1": ("VOL-v1", "IMPULSE-v1", "VWAPTR-v1"),
    "consensus_pullback_v1": ("TPREG-v1", "TRECLAIM-v1", "RSITREND-v1"),
    "consensus_range_v1": ("RANGE-v1", "BANDSWEEP-v1", "VOLFADE-v1"),
}
DIRECTIONS = {"LONG", "SHORT", "BUY", "SELL"}
FLAT = "ABSTAIN"

def evaluate(signals, *, minimum_agreement=2, veto_on_conflict=True):
    """Require >=2 constituent votes, never act on an opposing vote."""
    if not isinstance(signals, dict) or not 2 <= minimum_agreement <= 3:
        raise ValueError("invalid contemporaneous signals or quorum")
    result = {}
    for name, members in COMPOSITES.items():
        votes = []
        for member in members:
            side = signals.get(member)
            if side is None or side == FLAT or side == "HOLD":
                continue
            if side not in DIRECTIONS:
                raise ValueError("unknown direction")
            votes.append("LONG" if side == "BUY" else "SHORT" if side == "SELL" else side)
        count = Counter(votes)
        winning = count.most_common(1)[0] if count else None
        direction = winning[0] if winning and winning[1] >= minimum_agreement else FLAT
        if veto_on_conflict and len(count) > 1:
            direction = FLAT
        result[name] = {"signal": direction, "votes": len(votes),
                        "agreement": winning[1] if winning else 0,
                        "research_only": True, "orders_authorized": False}
    return result
