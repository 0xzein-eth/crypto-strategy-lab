"""Four new paper strategies: authentic prior/confirmed information only."""
import copy
import datetime as dt
import math
import unittest

import learner
import diverse_confirmed
import signals
import engine
import learner as research_allocator
from unittest.mock import patch

UTC=dt.timezone.utc


def bars(n=72):
    base=dt.datetime(2026,10,18,0,0,tzinfo=UTC)
    return [{"time":(base+dt.timedelta(minutes=15*i)).isoformat().replace("+00:00","Z"),
             "open":100.0,"high":100.3,"low":99.7,"close":100.0,
             "volume":100.0} for i in range(n)]


def signals_of(rows):
    return {x["strategy"]:x for x in signals.classify(rows)}


def payload(rows):
    result=[]
    for bar in reversed(rows):
        epoch=int(dt.datetime.fromisoformat(bar["time"].replace("Z","+00:00")).timestamp()*1000)
        result.append([str(epoch),str(bar["open"]),str(bar["high"]),
                       str(bar["low"]),str(bar["close"]),str(bar["volume"]),
                       "1","1","1"])
    return {"code":"0","data":result}


class DistinctForwardHypotheses(unittest.TestCase):
    def test_inside_bar_breakout_long_and_short(self):
        rows=bars()
        rows[-3].update(open=100,high=102,low=98,close=100)
        rows[-2].update(open=100,high=101,low=99,close=100)
        rows[-1].update(open=100,high=105,low=99.5,close=104,volume=250)
        long=signals_of(rows)
        self.assertIn("IBREAK-v1",long)
        self.assertEqual(long["IBREAK-v1"]["side"],"LONG")
        self.assertLessEqual(long["IBREAK-v1"]["evidence"]["frozen_signal_observation"]["child_width_ratio"],.75)
        down=bars()
        down[-3].update(open=100,high=102,low=98,close=100)
        down[-2].update(open=100,high=101,low=99,close=100)
        down[-1].update(open=100,high=100.5,low=95,close=96,volume=250)
        short=signals_of(down)
        self.assertEqual(short["IBREAK-v1"]["side"],"SHORT")
        # Formed signal must require an actual inside bar; do not coerce it.
        invalid=copy.deepcopy(rows)
        invalid[-2]["high"]=104
        self.assertNotIn("IBREAK-v1",signals_of(invalid))

    def test_band_extreme_must_reenter_on_next_confirmed_bar(self):
        rows=bars()
        rows[-2].update(open=100,high=101,low=91,close=92)
        rows[-1].update(open=92,high=102,low=91,close=101,volume=120)
        found=signals_of(rows)
        self.assertIn("BANDREV-v1",found)
        self.assertEqual(found["BANDREV-v1"]["side"],"LONG")
        self.assertLess(found["BANDREV-v1"]["evidence"]["frozen_signal_observation"]["previous_z20"],-1.8)
        # An isolated extreme does not count as a confirmed two-bar recovery.
        fake=copy.deepcopy(rows)
        fake[-1].update(open=92,high=93,low=90,close=91)
        self.assertNotIn("BANDREV-v1",signals_of(fake))
        down=bars()
        down[-2].update(open=100,high=109,low=99,close=108)
        down[-1].update(open=108,high=109,low=98,close=99,volume=120)
        self.assertEqual(signals_of(down)["BANDREV-v1"]["side"],"SHORT")

    def test_vwap_trend_uses_vwap_and_rsi_guards(self):
        rows=bars()
        f=signals.features(rows)
        f.update({
            "vwap20prev":100.5, "vwap20":100.6, "c_prev":100,
            "last_close":101, "last_open":100,
            "sma20":100.8, "sma50":100.2, "rsi14":61,
            "vol_ratio":1.35
        })
        out=diverse_confirmed.detect(rows,f)
        self.assertEqual([(r["strategy"],r["side"]) for r in out],[("VWAPTR-v1","LONG")])
        weak=dict(f,rsi14=40)
        self.assertFalse(any(x["strategy"]=="VWAPTR-v1"
                             for x in diverse_confirmed.detect(rows,weak)))
        down=dict(f,vwap20prev=99.4,vwap20=99.5,c_prev=100,
                  last_close=99,last_open=100,sma20=99.2,sma50=99.8,rsi14=39)
        short=diverse_confirmed.detect(rows,down)
        self.assertEqual([(r["strategy"],r["side"]) for r in short],[("VWAPTR-v1","SHORT")])

    def test_efficient_six_bar_trend_rejects_chop(self):
        z=bars()
        closes=[100,100.5,101,101.5,102,102.5,103]
        for b,c in zip(z[-7:],closes):
            b.update(open=c-.4,high=c+.25,low=c-.65,close=c,volume=120)
        out=signals_of(z)
        self.assertEqual(out["EFFTREND-v1"]["side"],"LONG")
        self.assertAlmostEqual(out["EFFTREND-v1"]["evidence"]["frozen_signal_observation"]["efficiency6"],1.0)
        flat=bars()
        oscillating=[100,101,100,101,100,101,100]
        for b,c in zip(flat[-7:],oscillating):
            b.update(open=c-.5,high=c+.25,low=c-.75,close=c,volume=120)
        self.assertNotIn("EFFTREND-v1",signals_of(flat))
        down=bars()
        falls=[100,99.5,99,98.5,98,97.5,97]
        for b,c in zip(down[-7:],falls):
            b.update(open=c+.4,high=c+.65,low=c-.25,close=c,volume=120)
        self.assertEqual(signals_of(down)["EFFTREND-v1"]["side"],"SHORT")

    def test_all_new_arms_frozen_and_registered(self):
        self.assertEqual(len(diverse_confirmed.ARMS),4)
        self.assertTrue(set(diverse_confirmed.ARMS).issubset(set(learner.ADVANCED)))
        z=bars()
        z[-3].update(high=102,low=98)
        z[-2].update(high=101,low=99)
        z[-1].update(high=105,low=99.5,close=104,volume=250)
        event=signals_of(z)["IBREAK-v1"]
        self.assertEqual(event["evidence"]["hypothesis_version"],diverse_confirmed.VERSION)
        self.assertEqual(event["evidence"]["bar_time"],z[-1]["time"])
        self.assertEqual(event["evidence"]["bar_span"],"15m confirmed OKX USDT-SWAP")
        self.assertTrue(event["evidence"]["research_only"])

    def test_new_versioned_paper_open_remains_fixed_horizon_and_history_immutable(self):
        bars_ = bars()
        bars_[-3].update(high=102,low=98)
        bars_[-2].update(high=101,low=99)
        bars_[-1].update(high=105,low=99.5,close=104,volume=250)
        now=dt.datetime(2026,10,18,18,0,tzinfo=UTC)
        snapshot={"symbol":"BTC", "price":104.0, "pct24h":2.1,
                  "quote_volume_24h":10_000_000.0,
                  "observed_at":engine.stamp(now),
                  "provider":"okx-swap", "market_type":"perpetual",
                  "instrument":"BTC-USDT-SWAP"}
        old={"LAB-999":{"id":"LAB-999","symbol":"ETH","provider":"okx-swap",
                        "status":"CLOSED","strategy":"BR-v3",
                        "created_at":engine.stamp(now-dt.timedelta(days=3)),
                        "horizon_hours":2}}
        before=copy.deepcopy(old)
        advanced=lambda sym,q:signals.classify(bars_)
        def pick(options, records, symbol, horizon, slot, rank, profile=None):
            item=next((x for x in options if x["strategy"]=="IBREAK-v1"),None)
            return item, "controlled_test_only"
        with patch.object(engine,"SYMBOLS",("BTC",)),patch.object(
                research_allocator,"choose",side_effect=pick):
            opens=engine.new_candidates(old,lambda s,p:snapshot,now,1500,1,
                                        advanced=advanced,
                                        reobserve=lambda s,p:snapshot,
                                        clock=lambda:now)
        self.assertEqual(old,before)
        self.assertEqual(len(opens),1)
        entry=opens[0]
        self.assertEqual(entry["strategy"],"IBREAK-v1")
        self.assertEqual(entry["evidence"]["hypothesis_version"],
                         diverse_confirmed.VERSION)
        self.assertIn(entry["horizon_hours"],(1,2,4,8,12,24))
        self.assertEqual((engine.parse(entry["evaluate_at"])-
                          engine.parse(entry["created_at"])).total_seconds(),
                         entry["horizon_hours"]*3600)
        self.assertEqual(entry["status"],"OPEN")
        self.assertTrue(entry["evidence"]["research_only"])
        engine.validate_open(entry)

    def test_unconfirmed_future_15m_bar_must_not_change_signal(self):
        rows=bars()
        rows[-3].update(high=102,low=98)
        rows[-2].update(high=101,low=99)
        rows[-1].update(high=105,low=99.5,close=104,volume=250)
        stamp=dt.datetime.fromisoformat(rows[-1]["time"].replace("Z","+00:00"))
        now=stamp+dt.timedelta(minutes=17)
        snap={"provider":"okx-swap","symbol":"BTC","market_type":"perpetual",
              "instrument":"BTC-USDT-SWAP","pct24h":2.0,
              "observed_at":now.isoformat().replace("+00:00","Z")}
        raw=payload(rows)
        before=signals.from_okx("BTC",snap,lambda url:raw,lambda:now)
        self.assertIn("IBREAK-v1",{x["strategy"] for x in before})
        # Intentionally huge unconfirmed and future data cannot enter signal.
        future=copy.deepcopy(rows[-1])
        next_start=stamp+dt.timedelta(minutes=15)
        future.update(time=next_start.isoformat().replace("+00:00","Z"),
                      close=100000,high=100001,low=99,volume=900000)
        extra=payload(rows+[future])
        extra["data"][0][-1]="0"
        after=signals.from_okx("BTC",snap,lambda url:extra,lambda:now)
        self.assertEqual(before,after)
        # Wrong provider never gains advanced signals.
        bad=dict(snap,provider="kraken-spot-proxy")
        self.assertEqual(signals.from_okx("BTC",bad,lambda url:raw,lambda:now),[])

if __name__=="__main__":
    unittest.main()
