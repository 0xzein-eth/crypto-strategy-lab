"""Read-only, fail-closed economic diagnostics for separate paper trading epochs.

Never merge historical $10k-per-position experiments with a funded wallet,
or use inspected backtests as proof of a winning strategy.
Run: python -m research_quality.audit
"""
import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def number(obj, field, *, default=None):
    value = obj.get(field, default)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field}: boolean is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field}: nonfinite value")
    return result

def historic_crypto(report):
    closed = int(number(report, "closed"))
    wins = int(number(report, "wins"))
    losses = int(number(report, "losses"))
    fees = number(report, "total_round_trip_fees_usd")
    net = number(report, "net_pnl_usd")
    if closed < 0 or wins + losses != closed or fees < 0:
        raise ValueError("invalid crypto ledger aggregates")
    gross = net + fees
    fee_per_trade = fees / closed if closed else None
    gross_per_trade = gross / closed if closed else None
    net_per_trade = net / closed if closed else None
    return {
        "status": "HISTORIC_UNFUNDED_EXPERIMENT_NOT_ACCOUNT_EQUITY",
        "closed": closed, "win_rate": wins / closed if closed else None,
        "net_usd": net, "fees_usd": fees, "before_fees_usd": round(gross, 2),
        "fee_per_close_usd": round(fee_per_trade, 5) if closed else None,
        "before_fee_per_close_usd": round(gross_per_trade, 5) if closed else None,
        "net_per_close_usd": round(net_per_trade, 5) if closed else None,
        "net_profit_factor": number(report, "profit_factor"),
        "price_edge_exceeds_friction": gross > fees if closed else False,
        "gross_price_edge_usd_per_close": round(gross / closed, 6) if closed else None,
        "fee_drag_usd_per_close": round(fees / closed, 6) if closed else None,
        "required_additional_gross_edge_usd_per_close_to_break_even": round(max(0, -net) / closed, 6) if closed else None,
        "gross_positive_but_net_negative": gross > 0 and net < 0,
        "cost_sensitivity_hypothetical_usd": {
            "fees_unchanged": round(net, 2),
            "fees_25pct_lower": round(gross - fees * 0.75, 2),
            "fees_50pct_lower": round(gross - fees * 0.50, 2),
            "fees_25pct_higher": round(gross - fees * 1.25, 2),
        },
        "prescription": "NO_AUTOMATIC_TRADE_SCALING_OR_STRATEGY_PROMOTION",
    }

def wallet(report):
    count = int(number(report, "closed_positions"))
    start = number(report, "initial_simulated_capital_usdt")
    equity = number(report, "current_simulated_equity_usdt")
    if count < 0 or start <= 0 or equity < 0:
        raise ValueError("invalid paper wallet")
    return {
        "status": "FORWARD_PAPER_NOT_LIVE",
        "closed_positions": count, "equity_usdt": equity,
        "return_pct": round((equity / start - 1) * 100, 6),
        "win_rate": number(report, "observed_closed_win_rate") if count else None,
        "funding_complete": bool(report.get("funding_source_complete") is True),
        "adequate_for_strategy_selection": False,
        "real_orders": 0,
    }

def equity(report):
    closed = int(number(report, "closed_trades"))
    initial = number(report, "initial_capital")
    current = number(report, "simulated_equity")
    if closed < 0 or initial <= 0 or current < 0:
        raise ValueError("invalid equity account")
    return {
        "status": "PROSPECTIVE_CASH_PAPER_EOD",
        "market": report["market"], "currency": report["currency"],
        "closed_trades": closed,
        "equity": current, "return_pct": round(100 * (current / initial - 1), 6),
        "win_rate": number(report, "win_rate") if closed else None,
        "profit_factor": number(report, "profit_factor") if closed else None,
        "adequate_for_strategy_selection": False,
        "real_orders": int(number(report, "real_orders")),
    }

def audit(root=ROOT):
    root = Path(root)
    def read(relative):
        file = root / relative
        if not file.is_file():
            return None
        return json.loads(file.read_text(encoding="utf-8"))
    result = {"version": "cross-lab-economic-integrity-v1",
              "no_real_orders_authorized": True,
              "historical_and_forward_returns_never_combined": True,
              "auto_promoted_champion": None,
              "markets": {}}
    for key, path, parser in (
        ("crypto_v8", "data/report.json", historic_crypto),
        ("crypto_v2", "v2_state/report.json", wallet),
        ("NASDAQ", "equity_state/NASDAQ/report.json", equity),
        ("LQ45", "equity_state/LQ45/report.json", equity),
    ):
        data = read(path)
        result["markets"][key] = parser(data) if data is not None else {
            "status": "NOT_RECORDED", "adequate_for_strategy_selection": False}
    return result

def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--root", type=Path, default=ROOT)
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    payload = json.dumps(audit(args.root), indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")

if __name__ == "__main__":
    main()
