"""End-to-end prospective lifecycle using deterministic MOCK quotes, no network."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import engine

class EndToEnd(unittest.TestCase):
    def test_first_and_second_run_replay_clean_and_no_backfill(self):
        start=dt.datetime(2026,10,8,2,0,tzinfo=dt.timezone.utc)
        sym_to_index={sym:i for i,sym in enumerate(engine.SYMBOLS)}
        now=[start]
        def clock():return now[0]
        def quote(symbol,provider,clock=None):
            if provider != "kraken-spot-proxy":
                raise RuntimeError("perpetual restricted in mock")
            i=sym_to_index[symbol]
            return {"symbol":symbol,"price":100+i+(1 if now[0]>start else 0),
                    "pct24h":(-2 if i%2==0 else 3),"quote_volume_24h":3_000_000,
                    "observed_at":engine.stamp(now[0]),"provider":provider,
                    "market_type":"spot_proxy","instrument":"XBTUSD" if symbol=="BTC" else symbol+"USD"}
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            (base/"data").mkdir()
            with patch.object(engine,"BASE",base),patch.object(engine,"EVENTS",base/"data"/"events"),\
                 patch.object(engine,"REPORT",base/"data"/"report.json"),\
                 patch.object(engine,"STATE",base/"data"/"state.json"),\
                 patch.object(engine,"quote",side_effect=quote):
                first=engine.run(6,clock=clock)
                self.assertEqual(first["added"],6)
                self.assertEqual(first["verified_events"],6)
                self.assertEqual(first["created"],6)
                self.assertEqual(first["closed"],0)
                now[0]=start+dt.timedelta(hours=25)
                second=engine.run(6,clock=clock)
                self.assertEqual(second["closed_this_run"],6)
                self.assertEqual(second["late_closed_this_run"],6)
                self.assertEqual(second["eligible_perpetual_timely"]["n"],0)
                self.assertEqual(second["created"],12)
                self.assertEqual(second["verified_events"],18)
                current,n,head,next_id=engine.replay(base)
                self.assertEqual((len(current),n,next_id),(12,18,128))
                self.assertTrue(head!=engine.PREV_ZERO)
                self.assertEqual(len({r["id"] for r in current.values()}),12)
                # Every historical full CLOSE and OPEN event is preserved in JSONL.
                lines=(base/"data"/"events"/"2026-10.jsonl").read_text().splitlines()
                self.assertEqual(len(lines),18)
                self.assertTrue((base/"data"/"report.json").exists())
                self.assertTrue((base/"data"/"state.json").exists())

if __name__=="__main__":unittest.main()
