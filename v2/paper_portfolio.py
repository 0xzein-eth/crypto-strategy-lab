"""Cash-constrained perpetual PAPER portfolio prototype, NO exchange calls.

Observed best-bid/ask top of book is an *input*, not an executed trade.
Assumed taker execution at the visible side is conservative but still
ignores queue, slippage beyond displayed depth, latency and actual fill.
This simulator is ISOLATED from the immutable v8 $10k experiment ledger.
"""
from copy import deepcopy
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json

UTC = dt.timezone.utc
CENT = Decimal("0.01")
HASH_ZERO = "0" * 64
SCHEMA = "v2-paper-cross-margin-wallet-1"


class OrderRejected(ValueError):
    """Fail closed; never imply an order was sent to a real exchange."""


def D(value):
    if isinstance(value, bool):
        raise OrderRejected("DATA_INVALID: boolean financial value")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise OrderRejected("DATA_INVALID: nonnumeric financial value") from exc
    if not result.is_finite():
        raise OrderRejected("DATA_INVALID: nonfinite financial value")
    return result


def ts(value):
    if isinstance(value, str):
        try:
            value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise OrderRejected("CLOCK_INVALID: datetime format") from exc
    if not isinstance(value, dt.datetime) or value.tzinfo is None:
        raise OrderRejected("CLOCK_INVALID: UTC-aware timestamp required")
    return value.astimezone(UTC)


def iso(value):
    return ts(value).isoformat().replace("+00:00", "Z")


def usd(value):
    return str(D(value).quantize(CENT))


def verify_quote(quote, *, symbol, now, max_age_seconds=180):
    """Verified venue, instrument, plausible fresh top-of-book and depth."""
    if not isinstance(quote, dict):
        raise OrderRejected("SOURCE_UNAVAILABLE: quote missing")
    if (quote.get("provider") != "okx-swap" or
            quote.get("market_type") != "perpetual" or
            quote.get("instrument") != symbol + "-USDT-SWAP" or
            quote.get("symbol") != symbol):
        raise OrderRejected("SOURCE_INVALID: wrong perpetual venue/instrument")
    observed = ts(quote.get("observed_at"))
    age = (ts(now) - observed).total_seconds()
    if not 0 <= age <= max_age_seconds:
        raise OrderRejected("SOURCE_STALE: future/late book observation")
    bid, ask = D(quote.get("bid")), D(quote.get("ask"))
    bid_size = D(quote.get("bid_size_base"))
    ask_size = D(quote.get("ask_size_base"))
    if bid <= 0 or ask < bid or bid_size <= 0 or ask_size <= 0:
        raise OrderRejected("SOURCE_INVALID: crossed/empty book")
    # In absence of full multi-level book depth, very wide quotes cannot be
    # used as plausible top-book executable entry prices.
    if (ask - bid) / ((ask + bid) / 2) > Decimal("0.005"):
        raise OrderRejected("SOURCE_INVALID: spread exceeds 0.50pct research cap")
    return {"symbol": symbol, "bid": bid, "ask": ask, "bid_size_base": bid_size,
            "ask_size_base": ask_size, "observed_at": iso(observed),
            "instrument": quote["instrument"]}


class PaperWallet:
    """Deterministic cross-margin PAPER ledger; no broker/order API adapter.

    Immutable hash-chained in-memory event journal is auditable; durable DB,
    exchange settlement and partial-book depth integration are *future*
    workstreams. Marks must be based on ACTUAL supplied quote observations.
    """

    def __init__(self, balance_usdt=1000, *, max_leverage=3,
                 taker_fee_rate="0.0005", maintenance_rate="0.005",
                 max_gross_equity_multiple=2):
        initial = D(balance_usdt)
        if not initial > 0:
            raise OrderRejected("CAPITAL_INVALID: positive paper balance required")
        lev = D(max_leverage)
        if not 1 <= lev <= 3:
            raise OrderRejected("RISK_GUARD: leverage >3 not supported")
        fee = D(taker_fee_rate)
        maintenance = D(maintenance_rate)
        cap = D(max_gross_equity_multiple)
        if not 0 <= fee < Decimal("0.02") or not 0 < maintenance < Decimal("0.1") or not 0 < cap <= 3:
            raise OrderRejected("RISK_GUARD: invalid fee, margin or exposure")
        self.initial_usdt = initial
        self.balance = initial
        self.leverage = lev
        self.fee_rate = fee
        self.maintenance_rate = maintenance
        self.max_gross_multiple = cap
        self._positions = {}
        self._closed = []
        self._events = []
        self._head = HASH_ZERO
        self._last_quotes = {}
        self._funding_receipts = set()
        self._total_fees = Decimal(0)
        self._total_funding_cash = Decimal(0)
        self._peak_observed_equity = initial
        self._max_observed_drawdown = Decimal(0)

    def _write(self, kind, when, payload):
        prior = self._head
        event = {"seq": len(self._events)+1, "prev_hash": prior,
                 "kind": kind, "observed_at": iso(when), "payload": payload}
        blob = json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False)
        event["hash"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        self._events.append(event)
        self._head = event["hash"]

    def audit_events(self):
        prev = HASH_ZERO
        for index, event in enumerate(self._events, 1):
            body = {k: v for k, v in event.items() if k != "hash"}
            actual = hashlib.sha256(json.dumps(body, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            if (event.get("seq") != index or event.get("prev_hash") != prev or
                    event.get("hash") != actual):
                raise ValueError("INTEGRITY_FAILURE: v2 portfolio event chain")
            prev = actual
        if prev != self._head:
            raise ValueError("INTEGRITY_FAILURE: last event head mismatch")
        return {"verified_events": len(self._events), "hash_head": self._head}

    def journal(self):
        return deepcopy(self._events)

    def positions(self):
        return deepcopy(self._positions)

    def closed_trades(self):
        return deepcopy(self._closed)

    def _view(self, now, quotes=None):
        # Never value open holdings using an unspecified/stale "latest" price.
        marks = dict(self._last_quotes)
        if quotes is not None:
            marks.update(quotes)
        unrealized = maintenance = gross = locked = Decimal(0)
        for p in self._positions.values():
            quote = verify_quote(marks.get(p["symbol"]), symbol=p["symbol"], now=now)
            executable_exit = quote["bid"] if p["side"] == "LONG" else quote["ask"]
            direction = Decimal(1) if p["side"] == "LONG" else Decimal(-1)
            unrealized += (executable_exit - p["entry_price"]) * p["quantity"] * direction
            exposure = p["quantity"] * executable_exit
            maintenance += exposure * self.maintenance_rate
            gross += p["opened_notional_usdt"]
            locked += p["initial_margin"]
        equity = self.balance + unrealized
        return {"equity": equity, "unrealized": unrealized,
                "gross_entry_notional": gross, "locked_margin": locked,
                "maintenance_margin": maintenance,
                "free_collateral": equity - locked,
                "liquidation_required": bool(self._positions and equity <= maintenance)}

    def mark(self, quotes, now):
        if not isinstance(quotes, dict):
            raise OrderRejected("SOURCE_INVALID: quote map")
        risk = self._view(now, quotes)
        for symbol, quote in quotes.items():
            verify_quote(quote, symbol=symbol, now=now)
        self._last_quotes.update(deepcopy(quotes))
        self._peak_observed_equity = max(self._peak_observed_equity, risk["equity"])
        self._max_observed_drawdown = max(
            self._max_observed_drawdown,
            self._peak_observed_equity - risk["equity"])
        return self.snapshot(now)

    def open(self, position_id, symbol, side, requested_notional_usdt,
             quote, now, *, allow_partial=False):
        when = ts(now)
        if not isinstance(position_id, str) or not position_id or position_id in self._positions or any(
                r["position_id"] == position_id for r in self._closed):
            raise OrderRejected("ORDER_INVALID: duplicate/empty paper ID")
        if side not in ("LONG", "SHORT") or not isinstance(symbol, str) or not symbol.isupper():
            raise OrderRejected("ORDER_INVALID: side / symbol")
        q = verify_quote(quote, symbol=symbol, now=when)
        requested = D(requested_notional_usdt)
        if not requested > 0:
            raise OrderRejected("ORDER_INVALID: positive requested notional")
        before = self._view(when, {symbol: quote})
        if before["liquidation_required"]:
            raise OrderRejected("RISK_GUARD: existing positions require liquidation")
        fill_px = q["ask"] if side == "LONG" else q["bid"]
        exit_px = q["bid"] if side == "LONG" else q["ask"]
        visible_base = q["ask_size_base"] if side == "LONG" else q["bid_size_base"]
        wanted_qty = requested / fill_px
        if visible_base < wanted_qty and not allow_partial:
            raise OrderRejected("LIQUIDITY_INSUFFICIENT: no guaranteed full top-book fill")
        qty = min(wanted_qty, visible_base)
        if qty <= 0 or (allow_partial and qty / wanted_qty < Decimal("0.1")):
            raise OrderRejected("LIQUIDITY_INSUFFICIENT: partial fill too small")
        filled = qty * fill_px
        margin = filled / self.leverage
        entry_fee = filled * self.fee_rate
        # Crossing from executable side to immediate liquidation side is a
        # cost in account equity even before a future mid-price movement.
        cross = (exit_px - fill_px) * qty * (
            Decimal(1) if side == "LONG" else Decimal(-1))
        after_open_equity = before["equity"] - entry_fee + cross
        if (after_open_equity <= before["maintenance_margin"] +
                qty * exit_px * self.maintenance_rate or
                after_open_equity - before["locked_margin"] - margin < 0):
            raise OrderRejected("MARGIN_INSUFFICIENT: paper cash/margin exhausted")
        if (before["gross_entry_notional"] + filled >
                after_open_equity * self.max_gross_multiple):
            raise OrderRejected("EXPOSURE_LIMIT: gross nominal exceeds equity cap")
        p = {"position_id": position_id, "symbol": symbol, "side": side,
             "opened_at": iso(when), "book_observed_at": q["observed_at"],
             "entry_price": fill_px, "quantity": qty,
             "opened_notional_usdt": filled, "requested_notional_usdt": requested,
             "initial_margin": margin, "entry_fee": entry_fee,
             "funding_cash_usdt": Decimal(0)}
        self._positions[position_id] = p
        self._last_quotes[symbol] = deepcopy(quote)
        self.balance -= entry_fee
        self._total_fees += entry_fee
        self._write("PAPER_OPEN", when, {
            "id": position_id, "instrument": q["instrument"], "side": side,
            "requested_usdt": str(requested), "filled_usdt": str(filled),
            "unfilled_usdt": str(requested-filled), "quantity_base": str(qty),
            "assumed_top_book_price": str(fill_px), "entry_fee_usdt": str(entry_fee),
            "margin_reserved_usdt": str(margin),
            "visible_book_not_a_real_fill": True})
        return {"position_id": position_id, "filled_notional_usdt": usd(filled),
                "unfilled_notional_usdt": usd(requested-filled),
                "partial": qty < wanted_qty, "paper_only": True}

    def settle_funding(self, position_id, rate, reference_mark_price,
                       settlement_time, now, *, settled=False):
        when, settlement = ts(now), ts(settlement_time)
        if not settled or settlement > when:
            raise OrderRejected("FUNDING_INVALID: only confirmed past settlement")
        p = self._positions.get(position_id)
        if p is None or settlement <= ts(p["opened_at"]):
            raise OrderRejected("FUNDING_INVALID: nonexistent / pre-entry position")
        key = (position_id, iso(settlement))
        if key in self._funding_receipts:
            raise OrderRejected("FUNDING_INVALID: duplicate settlement")
        if any(old_id == position_id and ts(old_time) >= settlement
               for old_id, old_time in self._funding_receipts):
            raise OrderRejected("FUNDING_INVALID: out-of-order settlement")
        rate = D(rate)
        price = D(reference_mark_price)
        if not -Decimal("0.1") <= rate <= Decimal("0.1") or price <= 0:
            raise OrderRejected("FUNDING_INVALID: bad settlement rate or mark")
        # Long pays when realized funding is positive; short receives.
        direction = Decimal(1) if p["side"] == "LONG" else Decimal(-1)
        cash = -direction * p["quantity"] * price * rate
        self.balance += cash
        p["funding_cash_usdt"] += cash
        self._total_funding_cash += cash
        self._funding_receipts.add(key)
        # Journal RECEIPT time, not a fake market observation at the
        # historical funding settlement; separate the exchange's settlement
        # timestamp from when the simulator was actually informed.
        self._write("SETTLED_FUNDING", when, {
            "id": position_id, "funding_settlement_at": iso(settlement),
            "realized_rate": str(rate),
            "reference_mark_usdt": str(price),
            "cash_delta_usdt": str(cash),
            "settled_provenance_required": True})
        return {"position_id": position_id, "settled_funding_cash_usdt": usd(cash)}

    def close(self, position_id, quote, now, *, forced_liquidation=False):
        when = ts(now)
        p = self._positions.get(position_id)
        if p is None:
            raise OrderRejected("ORDER_INVALID: cannot CLOSE unknown/already closed paper position")
        q = verify_quote(quote, symbol=p["symbol"], now=when)
        if when <= ts(p["opened_at"]):
            raise OrderRejected("CLOCK_INVALID: exit not after entry")
        risk = self._view(when, {p["symbol"]: quote})
        if risk["liquidation_required"] and not forced_liquidation:
            raise OrderRejected("RISK_GUARD: liquidation must be recorded explicitly")
        if forced_liquidation and not risk["liquidation_required"]:
            raise OrderRejected("LIQUIDATION_INVALID: margin condition not met")
        px = q["bid"] if p["side"] == "LONG" else q["ask"]
        gross = (px - p["entry_price"]) * p["quantity"] * (
            Decimal(1) if p["side"] == "LONG" else Decimal(-1))
        exit_fee = p["quantity"] * px * self.fee_rate
        # Existing initial margin is an encumbrance on the same cash, not
        # new money. Release it by removing the OPEN; do not credit it twice.
        self.balance += gross - exit_fee
        self._total_fees += exit_fee
        pnl = gross - p["entry_fee"] - exit_fee + p["funding_cash_usdt"]
        result = {"position_id": position_id, "side": p["side"],
                  "opened_at": p["opened_at"], "closed_at": iso(when),
                  "entry_price": str(p["entry_price"]),
                  "exit_price": str(px), "quantity_base": str(p["quantity"]),
                  "price_pnl_usdt": usd(gross),
                  "entry_fee_usdt": usd(p["entry_fee"]),
                  "exit_fee_usdt": usd(exit_fee),
                  "funding_cash_usdt": usd(p["funding_cash_usdt"]),
                  "net_pnl_usdt": usd(pnl),
                  "forced_liquidation": forced_liquidation,
                  "assumed_top_book_not_real_fill": True}
        del self._positions[position_id]
        self._closed.append(result)
        self._last_quotes[p["symbol"]] = deepcopy(quote)
        self._write("PAPER_LIQUIDATE" if forced_liquidation else "PAPER_CLOSE",
                    when, {"id": position_id, "bid_ask_exit_price": str(px),
                           "gross_pnl_usdt": str(gross),
                           "exit_fee_usdt": str(exit_fee),
                           "funding_cash_usdt": str(p["funding_cash_usdt"]),
                           "net_trade_pnl_usdt": str(pnl)})
        return deepcopy(result)

    def snapshot(self, now, *, quotes=None):
        risk = self._view(now, quotes)
        return {"schema": SCHEMA, "paper_only": True,
                "wallet_is_hypothetically_funded": True,
                "historical_v8_legacy_notional_reused": False,
                "real_fill_or_exchange_balance": False,
                "initial_cash_usdt": usd(self.initial_usdt),
                "cash_usdt": usd(self.balance),
                "unrealized_exit_side_pnl_usdt": usd(risk["unrealized"]),
                "equity_usdt": usd(risk["equity"]),
                "gross_opened_notional_usdt": usd(risk["gross_entry_notional"]),
                "reserved_initial_margin_usdt": usd(risk["locked_margin"]),
                "free_collateral_usdt": usd(risk["free_collateral"]),
                "maintenance_margin_usdt": usd(risk["maintenance_margin"]),
                "liquidation_required": risk["liquidation_required"],
                "open_positions": len(self._positions),
                "closed_positions": len(self._closed),
                "total_fees_usdt": usd(self._total_fees),
                "settled_funding_cash_usdt": usd(self._total_funding_cash),
                "observed_max_drawdown_usdt": usd(self._max_observed_drawdown),
                "real_order_submissions": 0,
                "fill_model": "hypothetical top-of-book crossing, no queue/latency guarantees",
                "journal": self.audit_events()}
