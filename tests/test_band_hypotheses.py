"""BANDREV-v1 funnel and independent BANDSWEEP-v1 prospective tests."""
import copy
import datetime as dt
import unittest

import band_hypotheses
import learner
import signals

UTC=dt.timezone.utc


def valid_bars(n=80):
    first=dt.datetime(2026,10,18,0,0,tzinfo=UTC)
    rows=[]
    for k in range(n):
        close=100.2 if k%2 else 99.8
        rows.append({
            "time":(first+dt.timedelta(minutes=15*k)).isoformat().replace("+00:00","Z"),
            "open":close, "high":101.0, "low":99.0,
            "close":close, "volume":100.0})
    return rows


def raw(rows):
    output=[]
    for row in reversed(rows):
        start=int(dt.datetime.fromisoformat(row["time"].replace("Z","+00:00")).timestamp()*1000)
        output.append([str(start),str(row["open"]),str(row["high"]),
                       str(row["low"]),str(row["close"]),str(row["volume"]),
                       "1","1","1"])
    return {"code":"0","data":output}


class BandOpportunityTests(unittest.TestCase):
    def test_distinct_new_hypothesis_long_and_short(self):
        z=valid_bars()
        z[-1].update(open=99.7,high=100.5,low=98.7,close=100.1,volume=180)
        funnel={}
        detected=signals.classify(z,diagnostics=funnel)
        arm=[r for r in detected if r["strategy"]=="BANDSWEEP-v1"]
        self.assertEqual(len(arm),1)
        self.assertEqual(arm[0]["side"],"LONG")
        self.assertEqual(arm[0]["evidence"]["hypothesis_version"],band_hypotheses.VERSION)
        self.assertEqual(arm[0]["evidence"]["bar_time"],z[-1]["time"])
        self.assertIn("BANDSWEEP-v1",learner.ADVANCED)
        self.assertEqual(funnel["bandsweep_confirmed_long"],1)
        z=valid_bars()
        z[-1].update(open=100.3,high=101.5,low=99.4,close=99.9,volume=180)
        arm=[r for r in signals.classify(z) if r["strategy"]=="BANDSWEEP-v1"]
        self.assertEqual(len(arm),1)
        self.assertEqual(arm[0]["side"],"SHORT")

    def test_no_fabricated_signal_without_real_sweep(self):
        z=valid_bars()
        diag={}
        no=signals.classify(z,diagnostics=diag)
        self.assertNotIn("BANDSWEEP-v1",{x["strategy"] for x in no})
        self.assertEqual(diag["bandsweep_confirmed_long"],0)
        self.assertEqual(diag["bandsweep_confirmed_short"],0)
        bad=valid_bars()
        bad[-1].update(open=99.7,high=100.5,low=98.7,close=100.1,volume=180)
        bad[-1]["low"]=99.55
        self.assertNotIn("BANDSWEEP-v1",{x["strategy"] for x in signals.classify(bad)})

    def test_previous_bandreentry_funnel_reports_missing_vs_valid(self):
        z=valid_bars()
        stages={}
        signals.classify(z,diagnostics=stages)
        self.assertEqual(stages["band_previous_std_positive"],1)
        self.assertEqual(stages["bandrev_previous_outside_long"],0)
        out=valid_bars()
        out[-2].update(open=100,high=101,low=89,close=90)
        out[-1].update(open=90,high=101,low=89,close=100.0,volume=160)
        metrics={}
        labels=signals.classify(out,diagnostics=metrics)
        self.assertEqual(metrics["bandrev_previous_outside_long"],1)
        self.assertEqual(metrics["bandrev_current_reentry_long"],1)
        self.assertEqual(metrics["bandrev_complete_long"],1)
        self.assertIn("BANDREV-v1",{item["strategy"] for item in labels})
        self.assertNotIn("BANDREV-v1",{x["strategy"] for x in signals.classify(z)})

    def test_unconfirmed_future_bars_do_not_contribute_to_funnel_or_entry(self):
        original=valid_bars()
        original[-1].update(open=99.7,high=100.5,low=98.7,close=100.1,volume=180)
        start=dt.datetime.fromisoformat(original[-1]["time"].replace("Z","+00:00"))
        observed=start+dt.timedelta(minutes=17)
        q={"provider":"okx-swap","symbol":"BTC","market_type":"perpetual",
           "instrument":"BTC-USDT-SWAP","pct24h":1.5,
           "observed_at":observed.isoformat().replace("+00:00","Z")}
        before={}
        a=signals.from_okx("BTC",q,lambda _:raw(original),lambda:observed,diagnostics=before)
        future=copy.deepcopy(original[-1])
        future.update(time=(start+dt.timedelta(minutes=15)).isoformat().replace("+00:00","Z"),
                      high=999,low=1,close=900,volume=999999)
        payload=raw(original+[future])
        payload["data"][0][-1]="0"
        after={}
        b=signals.from_okx("BTC",q,lambda _:payload,lambda:observed,diagnostics=after)
        self.assertEqual(a,b)
        self.assertEqual(before,after)
        self.assertEqual(before["bandsweep_confirmed_long"],1)
        # Source validation must have rejected any malformed historical candle.
        payload["data"][0][-1]="1"
        with self.assertRaises(ValueError):
            signals.from_okx("BTC",q,lambda _:payload,lambda:observed)

    def test_band_funnel_does_not_mutate_historical_input(self):
        rows=valid_bars()
        orig=copy.deepcopy(rows)
        f=signals.features(rows)
        found,flow=band_hypotheses.evaluate(rows,f)
        self.assertEqual(rows,orig)
        self.assertTrue(all(x["strategy"]=="BANDSWEEP-v1" for x in found))
        self.assertIn("bandrev_complete_long",flow)


if __name__=="__main__":
    unittest.main()
