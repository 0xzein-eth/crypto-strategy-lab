"""Synthetic offline contracts for Nasdaq USD / IDX LQ45 IDR PAPER ONLY."""
import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from equity_lab import universe,source,forward,research
from stock_lab import strategies,experimental

UTC=dt.timezone.utc


def dates(n=170,last=dt.date(2026,10,20)):
    out=[]
    day=last
    while len(out)<n:
        if day.weekday()<5:out.append(day.isoformat())
        day-=dt.timedelta(days=1)
    return list(reversed(out))


def market_rows(n=170,offset=0,last=dt.date(2026,10,20)):
    result=[]
    for i,date in enumerate(dates(n,last=last)):
        price=100+offset+i*.20+(i%7-3)*.8
        result.append({
            "date":date,"open":round(price-.15,5),
            "high":round(price+1.5,5),
            "low":round(price-1.5,5),
            "close":round(price,5),"volume":2500000,
        })
    return result


def when(market):
    if market=="NASDAQ":
        return dt.datetime(2026,10,20,21,10,tzinfo=ZoneInfo("America/New_York"))
    return dt.datetime(2026,11,19,19,10,tzinfo=ZoneInfo("Asia/Jakarta"))


def packet(market,symbol,offset=0):
    bars=market_rows(offset=offset,last=when(market).date())
    return {
      "symbol":symbol,"market":market,
      "currency":universe.MARKETS[market]["currency"],
      "provider":"unofficial-yahoo-chart",
      "is_nontradable_benchmark":False,
      "observed_at_utc":source.iso(when(market)),
      "last_complete_session":bars[-1]["date"],
      "history":bars,"history_sha256":source.sha(bars),
      "corporate_action_dates":{},"actual_exchange_fills":0,
    }


def feed(market,symbols=None):
    config=universe.MARKETS[market]
    symbols=symbols or config["symbols"][:10]
    p={symbol:packet(market,symbol,j*.01) for j,symbol in enumerate(symbols)}
    return {"market":market,"currency":config["currency"],
      "session":market_rows(last=when(market).date())[-1]["date"],
      "observed_at_utc":source.iso(when(market)),
      "membership_effective":config["membership_effective"],
      "membership_expiry":config["membership_expiry"],
      "no_real_orders":True,
      "stocks":p,"missing_symbols":{},"benchmark":None}


def yahoo(market,symbol,now,*,wrong_currency=False,index=False):
    last=(dt.date(2026,10,20) if market=="NASDAQ" else dt.date(2026,11,19))
    bars=market_rows(last=last)
    zone=ZoneInfo(universe.MARKETS[market]["timezone"])
    timestamps=[int(dt.datetime.combine(dt.date.fromisoformat(b["date"]),
                 dt.time(9,0),tzinfo=zone).timestamp()) for b in bars]
    q={k:[b[k] for b in bars] for k in ("open","high","low","close","volume")}
    return {"chart":{"error":None,"result":[{
         "meta":{"symbol":symbol,
                 "currency":("IDR" if market=="NASDAQ" else "USD") if wrong_currency else universe.MARKETS[market]["currency"],
                 "exchangeTimezoneName":universe.MARKETS[market]["timezone"],
                 "instrumentType":"INDEX" if index else "EQUITY"},
         "timestamp":timestamps,
         "indicators":{"quote":[q]}, "events":{},
    }]}}


class EquityUniverseTests(unittest.TestCase):
    def test_only_two_correct_currency_cohorts(self):
        self.assertTrue(universe.verify())
        self.assertEqual(len(universe.LQ45),45)
        self.assertEqual(len(universe.NASDAQ),25)
        self.assertEqual(universe.MARKETS["NASDAQ"]["currency"],"USD")
        self.assertEqual(universe.MARKETS["LQ45"]["currency"],"IDR")
        self.assertEqual(universe.MARKETS["LQ45"]["benchmark"],"^JKSE")
        self.assertIn("SMGR.JK",universe.LQ45)
        self.assertIn("ERAA.JK",universe.LQ45)
        self.assertIn("GGRM.JK",universe.LQ45)
        self.assertIn("PWON.JK",universe.LQ45)
        self.assertIn("INDY.JK",universe.LQ45)
        self.assertNotIn("MAPI.JK",universe.LQ45)
        self.assertNotIn("NCKL.JK",universe.LQ45)
        self.assertNotIn("PGEO.JK",universe.LQ45)
        self.assertNotIn("SCMA.JK",universe.LQ45)
        self.assertEqual(universe.MARKETS["LQ45"]["membership_effective"],"2026-11-18")
        self.assertEqual(universe.MARKETS["LQ45"]["membership_expiry"],"2027-01-29")

    def test_lq45_membership_is_effective_only_inside_declared_window(self):
        with self.assertRaisesRegex(ValueError,"MEMBERSHIP_NOT_YET_EFFECTIVE"):
            universe.market("LQ45",now=dt.datetime(2026,11,17,tzinfo=UTC))
        self.assertEqual(len(universe.market("LQ45",now=dt.datetime(2026,11,19,tzinfo=UTC))["symbols"]),45)
        with self.assertRaisesRegex(ValueError,"MEMBERSHIP_EXPIRED"):
            universe.market("LQ45",now=dt.datetime(2027,1,30,tzinfo=UTC))
        self.assertEqual(len(universe.market("NASDAQ")["symbols"]),25)

    def test_new_lq45_epoch_does_not_reuse_previous_ledger_directory(self):
        path,report,curve=forward.state_paths("LQ45")
        self.assertEqual(path.parent.name,"LQ45_2026-11-18")
        self.assertNotEqual(path.parent,forward.STATE/"LQ45")

    def test_wrong_currency_venue_and_universe_fail(self):
        for market in ("LQ45","NASDAQ"):
            symbol=universe.MARKETS[market]["symbols"][0]
            now=when(market)
            with self.assertRaisesRegex(ValueError,"SOURCE_INVALID"):
                source.parse(yahoo(market,symbol,now,wrong_currency=True),
                             symbol,market,now=now)
            with self.assertRaisesRegex(ValueError,"SOURCE_INVALID"):
                source.parse(yahoo(market,symbol,now),"^JKSE",market,now=now)

    def test_benchmark_only_index_and_no_stock_fill(self):
        for market in ("LQ45","NASDAQ"):
            cfg=universe.MARKETS[market]
            symbol=cfg["benchmark"]
            now=when(market)
            bm=source.parse(yahoo(market,symbol,now,index=True),symbol,market,
                            now=now,is_benchmark=True)
            self.assertTrue(bm["is_nontradable_benchmark"])
            with self.assertRaisesRegex(ValueError,"SOURCE_INVALID"):
                source.parse(yahoo(market,symbol,now,index=True),
                             cfg["symbols"][0],market,now=now)

    def test_intraday_current_partial_bar_discarded(self):
        for market in ("LQ45","NASDAQ"):
            cfg=universe.MARKETS[market]
            day=(dt.date(2026,10,21) if market=="NASDAQ" else dt.date(2026,11,20))
            before=dt.datetime.combine(day,dt.time(13),tzinfo=ZoneInfo(cfg["timezone"]))
            payload=yahoo(market,cfg["symbols"][0],before)
            bars=payload["chart"]["result"][0]["indicators"]["quote"][0]
            last=payload["chart"]["result"][0]["timestamp"][-1]
            # Add a mathematically coherent, but NOT completed, today's bar.
            today=dt.datetime.combine(day,dt.time(9),tzinfo=ZoneInfo(cfg["timezone"]))
            payload["chart"]["result"][0]["timestamp"].append(int(today.timestamp()))
            for k in bars:bars[k].append(bars[k][-1])
            bar=source.parse(payload,cfg["symbols"][0],market,now=before)
            expected="2026-10-20" if market=="NASDAQ" else "2026-11-19"
            self.assertEqual(bar["last_complete_session"],expected)
            self.assertNotEqual(last,int(today.timestamp()))


class EquityForwardTests(unittest.TestCase):
    def test_first_prospective_snapshot_writes_only_one_market(self):
        for market in ("LQ45","NASDAQ"):
            tick=forward.snapshot(feed(market))
            self.assertEqual(tick["currency"],universe.MARKETS[market]["currency"])
            events=forward.append([],tick)
            r=forward.replay(events,market)
            self.assertEqual(r["closed_trades"],0)
            self.assertIsNone(r["win_rate"])
            self.assertEqual(r["simulated_equity"],r["initial_capital"])
            self.assertTrue(r["no_automatic_champion_or_strategy_promotion"])

    def test_hash_mutation_and_mixed_currency_rejected(self):
        tick=forward.snapshot(feed("NASDAQ"))
        events=forward.append([],tick)
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"events.jsonl"
            file.write_text(source.canonical(events[0])+"\n")
            self.assertEqual(len(forward.read_events("NASDAQ",file)),1)
            changed=copy.deepcopy(events[0])
            changed["snapshot"]["assets"]["AAPL"]["history"][-1]["close"]*=2
            file.write_text(source.canonical(changed)+"\n")
            with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
                forward.read_events("NASDAQ",file)
        with self.assertRaisesRegex(ValueError,"MONEY_INTEGRITY"):
            forward.replay(events,"LQ45")

    def test_paper_entries_require_prior_frozen_buy(self):
        market="NASDAQ"
        original=forward.snapshot(feed(market))
        later=copy.deepcopy(original)
        later["session"]="2026-10-21"
        later["observed_at_utc"]=source.iso(dt.datetime(2026,10,21,22,tzinfo=
            ZoneInfo("America/New_York")))
        for symbol,row in later["assets"].items():
            b=copy.deepcopy(row["history"][-1])
            b["date"]=later["session"]
            row["history"]=row["history"][1:]+[b]
            row["last_bar"]=b
            row["history_sha256"]=source.sha(row["history"])
        # At this point original signals are frozen, not chosen after seeing
        # the later OPEN; no trade must exist before the second session.
        with patch("equity_lab.forward.strategies.signals",return_value={
              a:("BUY" if a=="TREND20_60" else "FLAT") for a in strategies.ARMS}):
            with patch("equity_lab.forward.experimental.signals",return_value={
                    a:"FLAT" for a in experimental.ARMS}):
                for tick in (original,later):
                    for row in tick["assets"].values():
                        row["signals"]={**strategies.signals(row["history"]),
                                        **experimental.signals(row["history"])}
                events=forward.append([],original)
                self.assertEqual(forward.replay(events,market)["open_positions"],[])
                events=forward.append(events,later)
                result=forward.replay(events,market)
                self.assertGreaterEqual(len(result["open_positions"]),1)
                self.assertLessEqual(len(result["open_positions"]),3)
                self.assertEqual(result["closed_trades"],0)
                self.assertEqual(result["real_orders"],0)


class EquityHistoryTests(unittest.TestCase):
    def test_fee_stress_additional_cost_never_increases_return(self):
        for market in ("NASDAQ","LQ45"):
            a,b=market_rows()[-3:-1]
            raw=research.returns(market,a,b)
            self.assertLess(raw,(b["open"]/a["open"]-1)*100)
            self.assertLess(raw-.25,raw)

    def test_study_uses_frozen_closes_and_never_promotes(self):
        for market in ("LQ45","NASDAQ"):
            symbols=universe.MARKETS[market]["symbols"][:9]
            stocks={s:packet(market,s,i*.10) for i,s in enumerate(symbols)}
            # 170 bars -> no valid historical 200-day evaluation; explicit.
            report=research.evaluate(market,stocks)
            self.assertFalse(report["out_of_sample_alpha_proven"])
            self.assertEqual(report["hypothesis_family_count"],14)
            self.assertFalse(report["observed_verified_history_symbols"])
            self.assertEqual(len(report["symbols_with_too_little_history"]),9)


if __name__=="__main__":
    unittest.main()
