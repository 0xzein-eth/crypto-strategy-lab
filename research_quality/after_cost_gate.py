"""Conservative research-only fee/impact hurdle. Does not open orders.

All quantities are percent of notional and predictions must be independently
versioned by their caller. Do not substitute realized future returns for a
forecast when deciding whether to trade.
"""
import math

def _finite_nonnegative(value, name):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name}: finite nonnegative number required")
    return float(value)

def evaluate(move_pct, entry_fee_pct, exit_fee_pct,
             spread_pct=0, impact_pct=0, buffer_pct=0):
    fields={"entry_fee_pct":entry_fee_pct,"exit_fee_pct":exit_fee_pct,
            "spread_pct":spread_pct,"impact_pct":impact_pct,"buffer_pct":buffer_pct}
    costs={name:_finite_nonnegative(value,name) for name,value in fields.items()}
    hurdle=sum(costs.values())
    if move_pct is None:
        status="NO_FORECAST"
    else:
        candidate=_finite_nonnegative(move_pct,"move_pct")
        status="RESEARCH_PASS" if candidate>hurdle*1.5 else "COST_VETO"
    return {"status":status,"cost_hurdle_pct":round(hurdle,10),
            "minimum_research_move_pct":round(hurdle*1.5,10),
            "components_pct":costs,"paper_orders":False,
            "live_orders":False,"model_validation_required":True}
