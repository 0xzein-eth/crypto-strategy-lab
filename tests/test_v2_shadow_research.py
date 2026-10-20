"""No-network, outcome-blind, future-only shadow cohort regression checks."""
import copy
import datetime as dt
from decimal import Decimal
import unittest
from unittest.mock import patch

from v2 import forward_paper as f
from v2 import shadow_research as shadow
from v2 import okx_observer_source as source

UTC=dt.timezone.utc
BASE=dt.datetime(2026,10,20,0,37,tzinfo=UTC)


def book(symbol,t,price="100",size="100"):
    p=Decimal(price)
    return {
        "provider":"okx-swap","market_type":"perpetual",
        "symbol":symbol,"instrument":symbol+"-USDT-SWAP",
        "observed_at":f.iso(t-dt.timedelta(seconds=5)),
        "bid":str(p),"ask":str(p+Decimal("0.05")),
        "bid_size_base":size,"ask_size_base":size,
    }


def signal(now,arm,side="LONG"):
    candle_end=now.replace(minute=30 if now.minute>=30 else 0,
                            second=0,microsecond=0)
    start=candle_end-dt.timedelta(minutes=15)
    return {"strategy":arm,"side":side,"evidence":{
        "bar_time":f.iso(start),
        "bar_span":"15m confirmed OKX USDT-SWAP",
        "atr14":1.5,"last_close":100,
        "source_version":"hypothesis-frozen-synthetic-test",
        "signal_rule":"confirmed candle synthetic test signal",
    }}


def tick(now,*,price="100",signals=()):
    frozen={symbol:[] for symbol in f.SYMBOLS}
    for symbol,arm,side in signals:
        frozen[symbol].append(signal(now,arm,side))
    return {"version":f.VERSION,"observed_at":f.iso(now),
            "books":{s:book(s,now,price) for s in f.SYMBOLS},
            "signals":frozen,"source_policy":"unit-test-synthetic-not-market",
            "market_orders_ever_submitted":False,
            "funding_settlement_history_verified":False}


def frozen_events(n,*,signals=(),price_at=None):
    events=[]
    for i in range(n):
        now=BASE+dt.timedelta(minutes=30*i)
        value=price_at(i) if price_at else "100"
        row=tick(now,price=value,signals=signals if i==0 else ())
        ev=f.seal(row,len(events)+1,
                  events[-1]["hash"] if events else f.HASH_ZERO)
        events.append(ev)
    return events


class BroaderEvidenceTests(unittest.TestCase):
    def test_catalog_static_and_not_a_winner_selected_subset(self):
        self.assertEqual(len(shadow.ARMS),26)
        self.assertIn("RSITREND-v1",shadow.ARMS)
        self.assertIn("FB-v3",shadow.ARMS)
        self.assertEqual(len(set(shadow.ARMS)),len(shadow.ARMS))
        self.assertEqual(set(f.STRATEGIES),{"FB-v3","VWAP-v1"})
        self.assertNotIn("RSITREND-v1",f.STRATEGIES)

    def test_all_arm_signal_is_a_shadow_not_a_wallet_trade(self):
        source_rows=[
            ("BTC","RSITREND-v1","SHORT"),
            ("ETH","IMPULSE-v1","LONG"),
            ("SOL","BANDSWEEP-v1","SHORT"),
        ]
        events=frozen_events(9,signals=source_rows,
                             price_at=lambda i: str(100+i*.2))
        wallet,curve=f.replay(events)
        self.assertEqual(wallet["prospective_paper_opens"],0)
        self.assertEqual(wallet["closed_positions"],0)
        self.assertEqual(wallet["current_simulated_equity_usdt"],"1000.00")
        self.assertEqual(len(curve),9)
        research=shadow.assess(events)
        self.assertEqual(research["source_observation_events"],9)
        self.assertEqual(len(research["closed_outcomes"]),3)
        for _,arm,_ in source_rows:
            m=research["per_arm"][arm]
            self.assertEqual(m["opportunities_from_confirmed_bars"],1)
            self.assertEqual(m["timely_matched_control_closed"],1)
            self.assertFalse(m["independent_out_of_sample_proof"])
        self.assertFalse(research["after_all_costs_alpha_proven"])
        self.assertFalse(research["promotion_authorized"])
        self.assertEqual(research["actual_paper_wallet_positions_created_by_this_study"],0)
        self.assertEqual(shadow.assess(events),research)

    def test_repeated_signal_same_bar_cannot_mint_extra_shadow_trials(self):
        events=frozen_events(9,signals=(("BTC","RSI-v1","LONG"),))
        tick2=copy.deepcopy(events[1]["tick"])
        tick2["signals"]["BTC"]=[copy.deepcopy(events[0]["tick"]["signals"]["BTC"][0])]
        events[1]=f.seal(tick2,2,events[0]["hash"])
        for i in range(2,len(events)):
            events[i]=f.seal(events[i]["tick"],i+1,events[i-1]["hash"])
        audit=shadow.assess(events)
        self.assertEqual(audit["per_arm"]["RSI-v1"]["opportunities_from_confirmed_bars"],1)
        self.assertEqual(audit["per_arm"]["RSI-v1"]["closed_shadow_hypotheses_all"],1)

    def test_no_future_quote_may_change_prior_shadow_result(self):
        series=frozen_events(10,signals=(("BTC","TP-v3","LONG"),),
                             price_at=lambda i:str(100+i*.2))
        earlier=shadow.assess(series[:9])
        altered=copy.deepcopy(series)
        altered[9]["tick"]["books"]["BTC"]["bid"]="70"
        altered[9]["tick"]["books"]["BTC"]["ask"]="70.05"
        altered[9]=f.seal(altered[9]["tick"],10,altered[8]["hash"])
        after=shadow.assess(altered[:9])
        self.assertEqual(earlier,after)
        self.assertEqual(earlier["per_arm"]["TP-v3"]["closed_shadow_hypotheses_all"],1)

    def test_late_actual_close_is_not_timely_alpha_evidence(self):
        first=frozen_events(1,signals=(("BTC","RSI-v1","LONG"),))
        late_now=BASE+dt.timedelta(hours=6)
        later=f.seal(tick(late_now,price="105"),2,first[0]["hash"])
        result=shadow.assess(first+[later])
        arm=result["per_arm"]["RSI-v1"]
        self.assertEqual(arm["closed_shadow_hypotheses_all"],1)
        self.assertEqual(arm["timely_matched_control_closed"],0)
        self.assertFalse(result["closed_outcomes"][0]["timely"])
        self.assertIsNone(arm["same_time_neutral_paired_delta_pct"])

    def test_no_liquidity_does_not_become_fake_executable_result(self):
        sample=tick(BASE,signals=(("BTC","RSI-v1","LONG"),))
        sample["books"]["BTC"]["bid_size_base"]="0.01"
        sample["books"]["BTC"]["ask_size_base"]="0.01"
        first=f.seal(sample,1,f.HASH_ZERO)
        final=shadow.assess([first])
        self.assertEqual(final["per_arm"]["RSI-v1"]["opportunities_from_confirmed_bars"],1)
        self.assertEqual(final["per_arm"]["RSI-v1"]["feasible_book_entry_opportunities"],0)
        self.assertEqual(final["per_arm"]["RSI-v1"]["unfillable_or_wide_entry_count"],1)
        self.assertEqual(final["per_arm"]["RSI-v1"]["closed_shadow_hypotheses_all"],0)

    def test_book_return_signs_and_same_time_hash_control(self):
        now=BASE
        a=book("BTC",now,price="100")
        b=book("BTC",now+dt.timedelta(hours=4),price="102")
        long,_=shadow.price_outcome(a,b,"LONG")
        short,_=shadow.price_outcome(a,b,"SHORT")
        self.assertGreater(long,0)
        self.assertLess(short,0)
        self.assertEqual(shadow.stable_side("frozen:signal"),shadow.stable_side("frozen:signal"))
        self.assertLess(long,2.0)  # fees and spread are real hypotheses costs

    def test_upstream_source_collects_all_registered_arms_no_winner_filter(self):
        at=BASE-dt.timedelta(seconds=5)
        quote=book("BTC",BASE)
        def public_mock(url):
            if "/market/ticker?" in url:
                return {"code":"0","data":[{
                    "instId":"BTC-USDT-SWAP",
                    "ts":str(int(at.timestamp()*1000)),
                    "last":"100","open24h":"99"}]}
            return {"code":"0","data":[]}
        fake=[
            signal(BASE,"RSI-v1"),
            signal(BASE,"FB-v3"),
            signal(BASE,"BANDSWEEP-v1"),
        ]
        with patch.object(source.signals,"from_okx",return_value=fake):
            got=source.one_signals("BTC",quote,getter=public_mock)
        self.assertEqual({i["strategy"] for i in got},
                         {"RSI-v1","FB-v3","BANDSWEEP-v1"})
        self.assertEqual(len(got),3)

    def test_wallet_two_strategies_remain_bounded_even_if_other_arms_exist(self):
        events=frozen_events(1,signals=(
            ("BTC","RSITREND-v1","LONG"),
            ("ETH","VWAP-v1","LONG"),
            ("SOL","FB-v3","LONG")))
        wallet,_=f.replay(events)
        self.assertEqual(wallet["prospective_paper_opens"],2)
        self.assertEqual(wallet["open_positions"],2)
        self.assertEqual(shadow.assess(events)["source_observation_events"],1)


if __name__=="__main__":
    unittest.main()
