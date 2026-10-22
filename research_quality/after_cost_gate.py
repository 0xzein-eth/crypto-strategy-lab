"""Shared read-only after-cost hypothesis evaluator. No trade execution."""
def evaluate(move_pct, entry_fee_pct, exit_fee_pct, spread_pct=0, impact_pct=0, buffer_pct=0):
    parts=[entry_fee_pct,exit_fee_pct,spread_pct,impact_pct,buffer_pct]
    if any(not isinstance(x,(int,float)) or x<0 or x!=x for x in parts):
        raise ValueError("invalid research costs")
    hurdle=sum(parts)
    if move_pct is None:
        return {"status":"NO_FORECAST", "cost_hurdle_pct":hurdle,"paper_orders":False}
    if not isinstance(move_pct,(int,float)) or move_pct!=move_pct:
        raise ValueError("invalid forecast")
    return {"status":"RESEARCH_PASS" if move_pct>hurdle*1.5 else "COST_VETO",
            "cost_hurdle_pct":hurdle,"paper_orders":False}
