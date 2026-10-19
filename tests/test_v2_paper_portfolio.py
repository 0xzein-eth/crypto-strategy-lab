"""No-network, immutable-journal, no-real-orders PAPER account regressions."""
from copy import deepcopy
import datetime as dt
from decimal import Decimal
import unittest

from v2.paper_portfolio import PaperWallet, OrderRejected

UTC=dt.timezone.utc
WHEN=dt.datetime(2026,10,19,10,0,tzinfo=UTC)


def quote(symbol="BTC",bid=100,ask=100.1,t=WHEN,
          bid_size_base=100,ask_size_base=100,provider="okx-swap"):
    return {"provider":provider,"market_type":"perpetual",
            "symbol":symbol,"instrument":symbol+"-USDT-SWAP",
            "observed_at":t.isoformat().replace("+00:00","Z"),
            "bid":bid,"ask":ask,
            "bid_size_base":bid_size_base,
            "ask_size_base":ask_size_base}


class PaperAccountTests(unittest.TestCase):
    def test_cannot_create_unfunded_notional_or_mint_reserved_margin(self):
        wallet=PaperWallet(balance_usdt=1000,max_leverage=3,
                           max_gross_equity_multiple=2)
        started=wallet.snapshot(WHEN)
        self.assertEqual(started["cash_usdt"],"1000.00")
        self.assertEqual(started["equity_usdt"],"1000.00")
        first=wallet.open("pos-1","BTC","LONG",1500,quote(),WHEN)
        self.assertFalse(first["partial"])
        now=wallet.snapshot(WHEN)
        self.assertEqual(now["open_positions"],1)
        self.assertEqual(now["reserved_initial_margin_usdt"],"500.00")
        self.assertLess(Decimal(now["equity_usdt"]),Decimal("1000"))
        with self.assertRaisesRegex(OrderRejected,"EXPOSURE_LIMIT"):
            wallet.open("pos-2","BTC","LONG",700,quote(),WHEN)
        self.assertEqual(wallet.snapshot(WHEN)["open_positions"],1)
        self.assertEqual(wallet.audit_events()["verified_events"],1)
        self.assertEqual(wallet.snapshot(WHEN)["real_order_submissions"],0)

    def test_bid_ask_crossing_fee_cash_identity_and_close(self):
        w=PaperWallet(1000)
        first=w.open("p","BTC","LONG",100,quote(),WHEN)
        self.assertEqual(first["filled_notional_usdt"],"100.00")
        mid=w.snapshot(WHEN)
        self.assertEqual(mid["cash_usdt"],"999.95")
        self.assertLess(Decimal(mid["equity_usdt"]),Decimal(mid["cash_usdt"]))
        close_when=WHEN+dt.timedelta(minutes=15)
        c=w.close("p",quote(bid=101.5,ask=101.6,t=close_when),close_when)
        self.assertEqual(w.snapshot(close_when)["open_positions"],0)
        self.assertEqual(w.snapshot(close_when)["reserved_initial_margin_usdt"],"0.00")
        cash=Decimal(w.snapshot(close_when)["cash_usdt"])
        net=Decimal(c["net_pnl_usdt"])
        self.assertAlmostEqual(float(cash),float(1000+net),places=2)
        self.assertTrue(Decimal(c["entry_fee_usdt"])>0)
        self.assertTrue(Decimal(c["exit_fee_usdt"])>0)
        self.assertEqual(w.audit_events()["verified_events"],2)
        self.assertEqual(w.snapshot(close_when)["closed_positions"],1)

    def test_short_side_spread_crossing_and_funding_reversal(self):
        t2=WHEN+dt.timedelta(minutes=30)
        a=PaperWallet()
        b=PaperWallet()
        a.open("a","BTC","LONG",100,quote(),WHEN)
        b.open("b","BTC","SHORT",100,quote(),WHEN)
        long_entry=a.snapshot(WHEN)
        short_entry=b.snapshot(WHEN)
        self.assertLess(Decimal(long_entry["equity_usdt"]),1000)
        self.assertLess(Decimal(short_entry["equity_usdt"]),1000)
        a.settle_funding("a","0.01",100.05,WHEN+dt.timedelta(minutes=15),t2,
                         settled=True)
        b.settle_funding("b","0.01",100.05,WHEN+dt.timedelta(minutes=15),t2,
                         settled=True)
        self.assertLess(Decimal(a.snapshot(t2,quotes={"BTC":quote(t=t2)})[
            "settled_funding_cash_usdt"]),0)
        self.assertGreater(Decimal(b.snapshot(t2,quotes={"BTC":quote(t=t2)})[
            "settled_funding_cash_usdt"]),0)
        a.close("a",quote(t=t2),t2)
        b.close("b",quote(t=t2),t2)
        self.assertLess(Decimal(a.snapshot(t2)["cash_usdt"]),
                        Decimal(b.snapshot(t2)["cash_usdt"]))
        self.assertEqual(a.audit_events()["verified_events"],3)
        with self.assertRaisesRegex(OrderRejected,"duplicate"):
            a.settle_funding("a","0.01",100.05,
                             WHEN+dt.timedelta(minutes=15),t2,settled=True)

    def test_funding_unsettled_and_future_are_never_invented(self):
        w=PaperWallet()
        w.open("x","BTC","LONG",100,quote(),WHEN)
        at=WHEN+dt.timedelta(minutes=20)
        with self.assertRaisesRegex(OrderRejected,"FUNDING_INVALID"):
            w.settle_funding("x",".01",100,at,at,settled=False)
        with self.assertRaisesRegex(OrderRejected,"FUNDING_INVALID"):
            w.settle_funding("x",".01",100,at,at-dt.timedelta(minutes=1),settled=True)
        with self.assertRaisesRegex(OrderRejected,"FUNDING_INVALID"):
            w.settle_funding("x",".01",100,WHEN,at,settled=True)
        self.assertEqual(w.snapshot(WHEN)["settled_funding_cash_usdt"],"0.00")

    def test_depth_insufficiency_is_rejected_or_explicitly_partial(self):
        limited=quote(bid=100,ask=100.1,ask_size_base="0.6")
        w=PaperWallet()
        with self.assertRaisesRegex(OrderRejected,"LIQUIDITY_INSUFFICIENT"):
            w.open("p","BTC","LONG",100,limited,WHEN)
        self.assertEqual(w.audit_events()["verified_events"],0)
        partial=w.open("p","BTC","LONG",100,limited,WHEN,
                       allow_partial=True)
        self.assertTrue(partial["partial"])
        self.assertGreater(Decimal(partial["unfilled_notional_usdt"]),0)
        self.assertEqual(w.audit_events()["verified_events"],1)

    def test_stale_wrong_venue_bad_book_and_id_rejected_without_order(self):
        w=PaperWallet()
        cases=[
            quote(provider="binance-futures"),
            quote(t=WHEN-dt.timedelta(minutes=15)),
            quote(t=WHEN+dt.timedelta(seconds=1)),
            quote(bid=102,ask=100),
            quote(bid=0,ask=100),
            quote(ask_size_base=0),
        ]
        for bad in cases:
            with self.subTest(bad=bad):
                with self.assertRaises(OrderRejected):
                    w.open("p","BTC","LONG",100,bad,WHEN)
                self.assertEqual(w.audit_events()["verified_events"],0)
        with self.assertRaises(OrderRejected):
            w.open("p","BTC","LONG",100,quote(),WHEN.replace(tzinfo=None))
        w.open("p","BTC","LONG",100,quote(),WHEN)
        with self.assertRaisesRegex(OrderRejected,"duplicate"):
            w.open("p","BTC","LONG",100,quote(),WHEN)

    def test_liquidation_guard_is_explicit_and_never_claims_real_fill(self):
        w=PaperWallet(balance_usdt=1000)
        w.open("p","BTC","LONG",1500,quote(bid=99.9,ask=100),WHEN)
        later=WHEN+dt.timedelta(minutes=15)
        crash=quote(bid=30,ask=30.05,t=later)
        marked=w.mark({"BTC":crash},later)
        self.assertTrue(marked["liquidation_required"])
        self.assertLess(Decimal(marked["equity_usdt"]),0)
        with self.assertRaisesRegex(OrderRejected,"RISK_GUARD"):
            w.open("new","BTC","LONG",10,crash,later)
        with self.assertRaisesRegex(OrderRejected,"LIQUIDATION_INVALID"):
            w.close("p",quote(bid=90,ask=90.05,t=later),later,
                    forced_liquidation=True)
        settled=w.close("p",crash,later,forced_liquidation=True)
        self.assertTrue(settled["forced_liquidation"])
        self.assertTrue(settled["assumed_top_book_not_real_fill"])
        self.assertEqual(w.snapshot(later)["open_positions"],0)
        self.assertEqual(w.audit_events()["verified_events"],2)

    def test_journal_is_hash_audited_deepcopied_and_does_not_change_v8(self):
        w=PaperWallet()
        w.open("p","BTC","LONG",100,quote(),WHEN)
        before=w.journal()
        before[0]["payload"]["requested_usdt"]="999999"
        self.assertEqual(w.audit_events()["verified_events"],1)
        # Direct internal corruption (should never occur) is detectable.
        w._events[0]["payload"]["requested_usdt"]="999999"
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            w.audit_events()

    def test_missing_fresh_quote_for_other_open_position_cannot_mark_wallet(self):
        w=PaperWallet()
        w.open("eth","ETH","LONG",100,quote(symbol="ETH"),WHEN)
        later=WHEN+dt.timedelta(minutes=4)
        with self.assertRaisesRegex(OrderRejected,"SOURCE_STALE"):
            w.open("btc","BTC","LONG",100,quote(t=later),later)
        self.assertEqual(w.audit_events()["verified_events"],1)
        newer_eth=quote(symbol="ETH",t=later)
        w.mark({"ETH":newer_eth},later)
        w.open("btc","BTC","LONG",100,quote(t=later),later)
        self.assertEqual(w.snapshot(later)["open_positions"],2)


if __name__=="__main__":
    unittest.main()
