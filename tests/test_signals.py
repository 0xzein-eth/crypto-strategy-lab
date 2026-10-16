import datetime as dt
import unittest
import signals
UTC=dt.timezone.utc

def bars(n=60):
    start=dt.datetime(2026,10,7,0,0,tzinfo=UTC)
    return [{"time":(start+dt.timedelta(minutes=15*i)).isoformat().replace("+00:00","Z"),
             "open":100.0,"high":101.0,"low":99.0,"close":100.0,"volume":100.0}
            for i in range(n)]

class SignalTests(unittest.TestCase):
    def test_confirmed_breakout(self):
        z=bars()
        z[-1].update(open=100,high=104,low=99,close=103,volume=200)
        found=signals.classify(z)
        self.assertTrue(any(x["strategy"]=="BR-v3" and x["side"]=="LONG" for x in found))
        self.assertTrue(all(x["evidence"]["bar_span"]=="15m confirmed OKX USDT-SWAP" for x in found))

    def test_oversold_mean_reversion(self):
        z=bars()
        z[-1].update(open=100,high=100,low=93,close=94,volume=200)
        self.assertTrue(any(x["strategy"]=="MR-v3" and x["side"]=="LONG"
                            for x in signals.classify(z)))

    def test_liquidity_sweep_reentry(self):
        z=bars()
        z[-1].update(open=100,high=101,low=95,close=100.4,volume=120)
        self.assertTrue(any(x["strategy"]=="LS-v3" and x["side"]=="LONG"
                            for x in signals.classify(z)))

    def test_failed_breakout_reentry(self):
        z=bars()
        z[-2].update(open=100,high=104,low=99,close=103)
        z[-1].update(open=103,high=103.5,low=100,close=100.5)
        self.assertTrue(any(x["strategy"]=="FB-v3" and x["side"]=="SHORT"
                            for x in signals.classify(z)))

    def test_ignore_incomplete_and_future_candles(self):
        z=bars(61)
        rows=[]
        for x in reversed(z):
            start=int(dt.datetime.fromisoformat(x["time"].replace("Z","+00:00")).timestamp()*1000)
            rows.append([str(start),str(x["open"]),str(x["high"]),str(x["low"]),
                         str(x["close"]),str(x["volume"]),"1","1","1"])
        rows[0][-1]="0"
        moment=dt.datetime.fromisoformat(z[-1]["time"].replace("Z","+00:00"))+dt.timedelta(minutes=16)
        selected=signals.parse_okx_candles({"code":"0","data":rows},moment)
        self.assertEqual(len(selected),60)
        self.assertEqual(selected[-1]["time"],z[-2]["time"])
        selected[-1]["close"]=200
        self.assertNotEqual(selected[-1]["close"],z[-1]["close"])

    def test_reject_gap(self):
        z=bars(61)
        z.pop(29)
        rows=[]
        for x in reversed(z):
            start=int(dt.datetime.fromisoformat(x["time"].replace("Z","+00:00")).timestamp()*1000)
            rows.append([str(start),str(x["open"]),str(x["high"]),str(x["low"]),
                         str(x["close"]),str(x["volume"]),"1","1","1"])
        moment=dt.datetime.fromisoformat(z[-1]["time"].replace("Z","+00:00"))+dt.timedelta(minutes=20)
        with self.assertRaisesRegex(ValueError,"gap"):
            signals.parse_okx_candles({"code":"0","data":rows},moment)

    def test_new_confirmed_cross_and_vwap_reclaim(self):
        z=bars()
        z[-1].update(open=100,high=102,low=99,close=101,volume=200)
        names={x["strategy"] for x in signals.classify(z)}
        self.assertIn("CROSS-v1",names)
        self.assertIn("VWAP-v1",names)

    def test_new_rsi_extreme_is_observable_without_future_candles(self):
        z=bars()
        z[-1].update(open=100,high=101,low=89,close=90,volume=200)
        f=signals.features(z)
        self.assertLess(f["rsi14"],22)
        signals_found=signals.classify(z)
        self.assertTrue(any(x["strategy"]=="RSI-v1" and x["side"]=="LONG"
                            for x in signals_found))

    def test_three_new_predeclared_candle_only_hypotheses(self):
        z=bars(70)
        z[-1].update(open=100,high=105,low=99.0,close=104,volume=180)
        names={x["strategy"] for x in signals.classify(z)}
        self.assertIn("DC-v1",names)
        self.assertIn("RSITREND-v1",names)
        self.assertIn("ATRCHAN-v1",names)
        for signal in signals.classify(z):
            if signal["strategy"] in ("DC-v1","RSITREND-v1","ATRCHAN-v1"):
                self.assertEqual(signal["side"],"LONG")
                self.assertEqual(signal["evidence"]["bar_time"],z[-1]["time"])
        z2=bars(70)
        z2[-1].update(open=100,high=101,low=95,close=96,volume=180)
        down={x["strategy"]:x["side"] for x in signals.classify(z2)}
        for name in ("DC-v1","RSITREND-v1","ATRCHAN-v1"):
            self.assertEqual(down.get(name),"SHORT")

    def test_added_paper_only_candle_arms_observed_without_future_data(self):
        z=bars(70)
        # Last completed bar must be the signal, not any forming future bar.
        z[-1].update(open=100,high=107,low=99,close=106,volume=250)
        decisions=signals.classify(z)
        self.assertTrue(any(x["strategy"]=="IMPULSE-v1" and x["side"]=="LONG"
                            for x in decisions))
        self.assertTrue(all(x["evidence"]["bar_time"]==z[-1]["time"]
                            for x in decisions))
        self.assertTrue(all(x["strategy"] in __import__("learner").ADVANCED
                            for x in decisions))

    def test_candle_age_rejects_old_signals_in_fresh_wall_clock_slot(self):
        z=bars(60)
        rows=[]
        for x in reversed(z):
            epoch=int(dt.datetime.fromisoformat(x["time"].replace("Z","+00:00")).timestamp()*1000)
            rows.append([str(epoch),str(x["open"]),str(x["high"]),str(x["low"]),
                         str(x["close"]),str(x["volume"]),"1","1","1"])
        latest=dt.datetime.fromisoformat(z[-1]["time"].replace("Z","+00:00"))
        with self.assertRaisesRegex(ValueError,"stale"):
            signals.parse_okx_candles({"code":"0","data":rows},
                                     latest+dt.timedelta(minutes=41))

    def test_confirmed_volume_fade_and_rsi_recovery(self):
        z=bars(70)
        z[-1].update(open=100,high=110,low=98,close=99,volume=250)
        found=signals.classify(z)
        self.assertTrue(any(x["strategy"]=="VOLFADE-v1"
                            and x["side"]=="SHORT" for x in found))
        down=bars(70)
        for i,index in enumerate(range(55,69)):
            price=99-i
            down[index].update(open=price+1,high=price+2,
                               low=price-1,close=price,volume=100)
        down[-1].update(open=86,high=93,low=85,close=92,volume=110)
        self.assertLess(signals.features(down)["rsi14prev"],30)
        self.assertGreaterEqual(signals.features(down)["rsi14"],30)
        recovery=signals.classify(down)
        self.assertTrue(any(x["strategy"]=="RSIREC-v1"
                            and x["side"]=="LONG" for x in recovery))
        self.assertTrue(all(x["evidence"]["bar_span"]=="15m confirmed OKX USDT-SWAP"
                            for x in recovery))

    def test_nonmatching_provider_not_fetched(self):
        called=[]
        output=signals.from_okx("BTC",{"provider":"kraken-spot-proxy"},
                                requester=lambda u:called.append(u),
                                clock=lambda:dt.datetime(2026,10,8,tzinfo=UTC))
        self.assertEqual(output,[])
        self.assertEqual(called,[])

if __name__=="__main__":unittest.main()
