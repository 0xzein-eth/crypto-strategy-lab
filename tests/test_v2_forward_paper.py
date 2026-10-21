"""Strict offline forward-replay tests; no API credentials, orders or backfills."""
import copy
import datetime as dt
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from v2 import forward_paper as f
from v2 import okx_observer_source as source

UTC=dt.timezone.utc
BASE=dt.datetime(2026,10,20,0,7,tzinfo=UTC)


def quote(symbol, now, *, bid="100",ask="100.05",bid_contracts="100"):
    return {
        "provider":"okx-swap", "market_type":"perpetual",
        "symbol":symbol, "instrument":symbol+"-USDT-SWAP",
        "observed_at":f.iso(now-dt.timedelta(seconds=5)),
        "bid":bid, "ask":ask,
        "bid_size_base":bid_contracts,"ask_size_base":bid_contracts,
    }


def candidate(now, strategy="FB-v3", side="LONG"):
    bar = now.replace(minute=30 if now.minute>=30 else 0,second=0,microsecond=0)
    # Last confirmed candle ended at :00 or :30, opened 15m earlier.
    bar-=dt.timedelta(minutes=15)
    return {"strategy":strategy,"side":side,"evidence":{
        "bar_time":f.iso(bar),
        "bar_span":"15m confirmed OKX USDT-SWAP",
        "last_close":100.0,"atr14":1.4,
        "signal_rule":"synthetic validated test fixture only",
        "source_version":"confirmed-15m-v1",
    }}


def tick(now, *, price=100, signals=("BTC",), special_quote=None):
    books={x:quote(x,now,bid=str(price),ask=str(price+.05)) for x in f.SYMBOLS}
    if special_quote:
        books.update(special_quote)
    sigs={x:[] for x in f.SYMBOLS}
    for symbol in signals:
        sigs[symbol]=[candidate(now)]
    return {"version":f.VERSION,"observed_at":f.iso(now),
            "books":books,"signals":sigs,
            "market_orders_ever_submitted":False,
            "funding_settlement_history_verified":False,
            "source_policy":"unit-test-public-frozen-inputs-only"}


def build(count=9):
    events=[]
    for idx in range(count):
        now=BASE+dt.timedelta(minutes=30*idx)
        t=tick(now,price=100+0.1*idx,
               signals=("BTC","ETH") if idx==0 else ())
        event=f.seal(t,len(events)+1,events[-1]["hash"] if events else f.HASH_ZERO)
        events.append(event)
    return events


class SlotDeduplicationTests(unittest.TestCase):
    def test_fast_skip_same_real_half_hour_without_any_api_call(self):
        existing=build(1)
        self.assertTrue(f.already_observed_slot(
            existing,BASE+dt.timedelta(minutes=12)))
        self.assertFalse(f.already_observed_slot(
            existing,BASE+dt.timedelta(minutes=30)))
        self.assertFalse(f.already_observed_slot([],BASE))
        with self.assertRaisesRegex(ValueError,"CLOCK_INTEGRITY"):
            f.already_observed_slot(existing,BASE-dt.timedelta(hours=1))


class DurableForwardWalletTests(unittest.TestCase):
    def test_one_cash_account_nonreset_across_periods_and_fixed_four_hour_close(self):
        ev=build()
        first, curve=f.replay(ev[:1])
        self.assertEqual(first["observations"],1)
        self.assertEqual(first["open_positions"],2)
        self.assertEqual(first["prospective_paper_opens"],2)
        self.assertLess(Decimal(curve[0]["equity_usdt"]),1000)
        self.assertEqual(first["research_status"],
                         "EXPLORATORY_FORWARD_PLUMBING_NOT_VALIDATED_ALPHA")
        half, part=f.replay(ev[:6])
        self.assertEqual(half["open_positions"],2)
        self.assertGreater(Decimal(part[-1]["equity_usdt"]),Decimal(part[0]["equity_usdt"]))
        last, daily=f.replay(ev)
        self.assertEqual(last["open_positions"],0)
        self.assertEqual(last["closed_positions"],2)
        self.assertEqual(len(daily),9)
        self.assertEqual(last["observed_max_drawdown_usdt"],first["observed_max_drawdown_usdt"])
        self.assertGreater(Decimal(last["current_simulated_cash_usdt"]),1000)
        self.assertEqual(last["current_simulated_cash_usdt"],last["current_simulated_equity_usdt"])
        self.assertEqual(last["account_journal"]["verified_events"],4)
        self.assertEqual(last["real_order_submissions"],0)
        self.assertFalse(last["funding_source_complete"])
        self.assertFalse(last["after_all_costs_performance_proven"])
        self.assertTrue(last["simulated_wallet_excludes_unverified_funding"])
        again,_=f.replay(ev)
        self.assertEqual(last,again)

    def test_deterministic_hash_chain_and_duplicate_slot_fail_closed(self):
        ev=build(2)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"sample.jsonl"
            p.write_text("".join(f.canonical(r)+"\n" for r in ev),encoding="utf-8")
            self.assertEqual(len(f.read_events(p)),2)
            broken=copy.deepcopy(ev)
            broken[1]["tick"]["books"]["BTC"]["bid"]="100000000"
            p.write_text("".join(f.canonical(r)+"\n" for r in broken),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
                f.read_events(p)
        with self.assertRaisesRegex(ValueError,"CLOCK_INTEGRITY"):
            f.evaluate_candidate(ev, tick(BASE+dt.timedelta(minutes=31)))
        with self.assertRaisesRegex(ValueError,"CLOCK_INTEGRITY"):
            f.replay([ev[0],f.seal(tick(BASE+dt.timedelta(minutes=1)),2,ev[0]["hash"])])

    def test_missing_cross_market_book_prevents_false_equity(self):
        t=tick(BASE)
        del t["books"]["ETH"]
        with self.assertRaisesRegex(ValueError,"SOURCE_UNAVAILABLE"):
            f.validate_tick(t)
        t=tick(BASE)
        t["books"]["SOL"]["observed_at"]=f.iso(BASE-dt.timedelta(minutes=4))
        with self.assertRaisesRegex(Exception,"SOURCE_STALE"):
            f.validate_tick(t)
        t=tick(BASE)
        t["books"]["BTC"]["provider"]="binance-futures"
        with self.assertRaisesRegex(Exception,"SOURCE_INVALID"):
            f.validate_tick(t)

    def test_future_or_stale_confirmed_signal_rejected(self):
        t=tick(BASE)
        t["signals"]["BTC"][0]["evidence"]["bar_time"]=f.iso(BASE+dt.timedelta(minutes=15))
        with self.assertRaisesRegex(ValueError,"CLOCK_INTEGRITY"):
            f.validate_tick(t)
        t=tick(BASE)
        t["signals"]["BTC"][0]["evidence"]["bar_time"]=f.iso(
            BASE-dt.timedelta(hours=2))
        with self.assertRaisesRegex(ValueError,"CLOCK_INTEGRITY"):
            f.validate_tick(t)
        t=tick(BASE)
        t["signals"]["BTC"][0]["strategy"]="UNREGISTERED_WINNER"
        with self.assertRaisesRegex(ValueError,"SIGNAL_INVALID"):
            f.validate_tick(t)

    def test_spread_and_atr_cost_gates_abstain_without_rewriting(self):
        bad=tick(BASE,signals=("BTC",),special_quote={
            "BTC":quote("BTC",BASE,bid="100",ask="100.2")})
        # Top-level source is valid, but explicit 20bps research gate abstains.
        report,curve=f.replay([f.seal(bad,1,f.HASH_ZERO)])
        self.assertEqual(report["prospective_paper_opens"],0)
        self.assertEqual(report["research_veto_counts"]["spread_exceeds_research_cap"],1)
        small=tick(BASE)
        small["signals"]["BTC"][0]["evidence"]["atr14"]=.00001
        report,_=f.replay([f.seal(small,1,f.HASH_ZERO)])
        self.assertEqual(report["prospective_paper_opens"],0)
        self.assertIn("atr_movement_scale_below_cost_hurdle",report["research_veto_counts"])

    def test_no_leverage_spiral_even_when_every_symbol_offers_signal(self):
        two=tick(BASE,signals=("BTC","ETH","SOL"))
        report,_=f.replay([f.seal(two,1,f.HASH_ZERO)])
        self.assertEqual(report["prospective_paper_opens"],2)
        self.assertEqual(report["open_positions"],2)
        self.assertEqual(report["research_veto_counts"]["two_position_wallet_cap"],1)
        self.assertLessEqual(Decimal(report["current_simulated_equity_usdt"]),1000)

    def test_market_order_route_is_absent_and_funding_never_invented(self):
        self.assertFalse(hasattr(f,"submit_order"))
        report,_=f.replay([])
        self.assertEqual(report["observations"],0)
        self.assertEqual(report["current_simulated_equity_usdt"],"1000")
        self.assertEqual(report["real_order_submissions"],0)
        self.assertFalse(report["funding_source_complete"])


class PublicSourceContractTests(unittest.TestCase):
    def test_book_contract_size_is_converted_to_base_coin(self):
        def getter(url):
            if "/public/instruments?" in url:
                return {"code":"0","data":[{
                    "instId":"BTC-USDT-SWAP","instType":"SWAP",
                    "ctType":"linear","ctValCcy":"BTC","state":"live",
                    "settleCcy":"USDT","ctVal":"0.01"}]}
            if "/market/books?" in url:
                return {"code":"0","data":[{
                    "ts":str(int((BASE-dt.timedelta(seconds=5)).timestamp()*1000)),
                    "bids":[["100","50","0","1"]],
                    "asks":[["100.05","40","0","1"]],
                }]}
            raise AssertionError("unexpected public endpoint "+url)
        q=source.one_book("BTC",BASE,getter=getter)
        self.assertEqual(q["bid_size_base"],"0.50")
        self.assertEqual(q["ask_size_base"],"0.40")
        self.assertEqual(q["contracts_value_in_base"],"0.01")
        self.assertTrue(q["instrument_metadata_verified"])

    def test_scheduled_default_time_path_uses_post_fetch_clock(self):
        # Regression: current_tick() passes now=None to one_book(), so it
        # must validate against the post-fetch clock, not None.
        def getter(url):
            if "/public/instruments?" in url:
                return {"code":"0","data":[{
                    "instId":"BTC-USDT-SWAP","instType":"SWAP",
                    "ctType":"linear","ctValCcy":"BTC","state":"live",
                    "settleCcy":"USDT","ctVal":"0.01"}]}
            if "/market/books?" in url:
                return {"code":"0","data":[{
                    "ts":str(int((BASE-dt.timedelta(seconds=5)).timestamp()*1000)),
                    "bids":[["100","50","0","1"]],
                    "asks":[["100.05","40","0","1"]]}]}
            raise AssertionError("Unexpected URL "+url)
        sample=source.one_book("BTC",None,getter=getter,clock=lambda:BASE)
        self.assertEqual(sample["bid_size_base"],"0.50")
        self.assertEqual(sample["ask_size_base"],"0.40")
        self.assertEqual(sample["provider"],"okx-swap")
        with self.assertRaisesRegex(Exception,"SOURCE_STALE"):
            source.one_book("BTC",None,getter=getter,
                            clock=lambda:BASE+dt.timedelta(minutes=4))

    def test_wrong_contract_denomination_and_private_endpoint_fail_closed(self):
        def bad(url):
            return {"code":"0","data":[{
                "instId":"BTC-USDT-SWAP","instType":"SWAP",
                "ctType":"inverse","ctValCcy":"USD","state":"live",
                "settleCcy":"USDT","ctVal":"100"}]}
        with self.assertRaisesRegex(ValueError,"SOURCE_INVALID"):
            source.instrument_contract_base("BTC",getter=bad)
        with self.assertRaisesRegex(ValueError,"SOURCE_INVALID"):
            source.public_json("https://www.okx.com/api/v5/trade/order?foo=bar")
        with self.assertRaises(ValueError):
            source.endpoint("/market/books","FAKE")

if __name__=="__main__":
    unittest.main()
