"""Authenticated v2 PAPER recovery: replay economics, not only SHA-256."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from v2.paper_portfolio import PaperWallet, OrderRejected

UTC=dt.timezone.utc
T0=dt.datetime(2026,10,19,8,0,tzinfo=UTC)


def book(symbol="BTC", at=T0, bid=100, ask=100.1,
         bid_size=100,ask_size=100):
    return {"provider":"okx-swap","market_type":"perpetual",
            "symbol":symbol,"instrument":symbol+"-USDT-SWAP",
            "observed_at":at.isoformat().replace("+00:00","Z"),
            "bid":bid,"ask":ask,"bid_size_base":bid_size,
            "ask_size_base":ask_size}


def rehash(document):
    prev="0"*64
    for i,event in enumerate(document["events"],1):
        event["seq"]=i
        event["prev_hash"]=prev
        body={k:v for k,v in event.items() if k!="hash"}
        event["hash"]=hashlib.sha256(json.dumps(
            body,sort_keys=True,separators=(",",":"),
            allow_nan=False).encode()).hexdigest()
        prev=event["hash"]
    document["expected_head"]=prev


class DurabilityTests(unittest.TestCase):
    def test_save_load_replay_open_mark_partial_funding_close(self):
        w=PaperWallet(balance_usdt=1000)
        opened=w.open("btc-1","BTC","LONG",100,
                      book(ask_size=".6"),T0,allow_partial=True)
        self.assertTrue(opened["partial"])
        t1=T0+dt.timedelta(minutes=2)
        w.mark({"BTC":book(at=t1,bid=101,ask=101.1)},t1)
        settled=T0+dt.timedelta(minutes=1)
        w.settle_funding("btc-1",".01",101,settled,t1,settled=True)
        t2=T0+dt.timedelta(minutes=4)
        w.close("btc-1",book(at=t2,bid=102,ask=102.1),t2)
        expected=w.document()
        self.assertEqual(w.audit_events()["verified_events"],4)
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/"state"/"paper-wallet.json"
            w.save_atomic(file)
            recovered=PaperWallet.load_verified(file)
            self.assertEqual(recovered.document(),expected)
            self.assertEqual(recovered.snapshot(t2)["cash_usdt"],
                             w.snapshot(t2)["cash_usdt"])
            self.assertEqual(recovered.snapshot(t2)["open_positions"],0)
        self.assertTrue(expected["ledger_is_not_v8_events"])
        self.assertEqual(expected["real_orders"],0)

    def test_fresh_mark_is_durable_for_successor_open_on_another_market(self):
        w=PaperWallet()
        w.open("eth","ETH","LONG",100,book("ETH"),T0)
        later=T0+dt.timedelta(minutes=4)
        with self.assertRaisesRegex(OrderRejected,"SOURCE_STALE"):
            w.open("btc","BTC","SHORT",100,book("BTC",later),later)
        w.mark({"ETH":book("ETH",later)},later)
        w.open("btc","BTC","SHORT",100,book("BTC",later),later)
        restored=PaperWallet.from_document(w.document())
        self.assertEqual(restored.document(),w.document())
        self.assertEqual(restored.snapshot(later)["open_positions"],2)
        self.assertEqual(restored.audit_events()["verified_events"],3)

    def test_corrupt_hash_chain_or_fake_balances_are_refused(self):
        w=PaperWallet()
        w.open("x","BTC","LONG",100,book(),T0)
        d=w.document()
        fake=copy.deepcopy(d)
        fake["events"][0]["payload"]["filled_usdt"]="100000000000"
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            PaperWallet.from_document(fake)
        fake2=copy.deepcopy(d)
        fake2["expected_cash_balance_usdt"]="999999999"
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            PaperWallet.from_document(fake2)

    def test_rehashed_forged_close_pnl_detected_by_deterministic_replay(self):
        w=PaperWallet()
        w.open("x","BTC","LONG",100,book(),T0)
        t1=T0+dt.timedelta(minutes=15)
        w.close("x",book(at=t1,bid=103,ask=103.1),t1)
        fake=copy.deepcopy(w.document())
        fake["events"][1]["payload"]["net_trade_pnl_usdt"]="999999"
        rehash(fake)  # valid cryptographic chain but impossible economics
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            PaperWallet.from_document(fake)

    def test_forced_liquidation_recovered_with_true_book_sequence(self):
        w=PaperWallet()
        w.open("crash","BTC","LONG",1500,
               book(bid=99.9,ask=100),T0)
        t1=T0+dt.timedelta(minutes=20)
        q=book(at=t1,bid=30,ask=30.05)
        w.mark({"BTC":q},t1)
        w.close("crash",q,t1,forced_liquidation=True)
        restored=PaperWallet.from_document(w.document())
        self.assertEqual(restored.document(),w.document())
        self.assertTrue(restored.closed_trades()[0]["forced_liquidation"])
        self.assertEqual(restored.snapshot(t1)["open_positions"],0)


if __name__=="__main__":
    unittest.main()
