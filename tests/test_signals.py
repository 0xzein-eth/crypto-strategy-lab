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

    def test_nonmatching_provider_not_fetched(self):
        called=[]
        output=signals.from_okx("BTC",{"provider":"kraken-spot-proxy"},
                                requester=lambda u:called.append(u),
                                clock=lambda:dt.datetime(2026,10,8,tzinfo=UTC))
        self.assertEqual(output,[])
        self.assertEqual(called,[])

if __name__=="__main__":unittest.main()
