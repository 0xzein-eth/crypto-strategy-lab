"""Offline counterexamples for the 2026-10-22 integrity/leakage audit."""
import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from equity_lab import forward as f, source, universe, research
from stock_lab import strategies, experimental
from research_quality import equity_ensemble, audit as economic


def bars(n=260):
    days=[]
    day=dt.date(2026,10,22)
    while len(days)<n:
        if day.weekday()<5:days.append(day.isoformat())
        day-=dt.timedelta(days=1)
    return [{"date":day,"open":100+i*.1,"high":102+i*.1,
             "low":98+i*.1,"close":100+i*.1,"volume":2000000}
            for i,day in enumerate(reversed(days))]


def forced_signals(rows):
    # At the first EOD, only AAPL proposes a buy. At subsequent EODs,
    # all tickers propose buys, leaving room to test the next OPEN budget.
    buy=rows[-1]["date"]!="2026-10-20" or rows[-1]["open"]<150
    return {arm:("BUY" if arm==strategies.ARMS[0] and buy else "FLAT")
            for arm in strategies.ARMS}


def tick(day,*,close_factor=1,volume=2000000,legacy=False):
    stocks={}
    for j,symbol in enumerate(universe.NASDAQ[:8]):
        history=[copy.deepcopy(b) for b in bars() if b["date"]<=day]
        for row in history:
            for key in ("open","high","low","close"):row[key]+=j*100
        row=history[-1]
        row["close"]*=close_factor
        row["low"]=min(row["low"],row["close"])
        row["high"]=max(row["high"],row["close"])
        row["volume"]=volume
        stocks[symbol]={"market":"NASDAQ","currency":"USD",
            "history":history,"history_sha256":source.sha(history),
            "last_complete_session":day,"corporate_action_dates":{}}
    config=universe.MARKETS["NASDAQ"]
    result=f.snapshot({"market":"NASDAQ","currency":"USD","session":day,
        "observed_at_utc":day+"T23:30:00Z", "no_real_orders":True,
        "membership_effective":config["membership_effective"],
        "membership_expiry":config["membership_expiry"],
        "stocks":stocks,"benchmark":None,"missing_symbols":{}})
    if legacy:result["schema"]=f.LEGACY_VERSION
    return result


class EquityAuditRegressions(unittest.TestCase):
    def setUp(self):
        self.basic=patch.object(strategies,"signals",side_effect=forced_signals)
        self.extra=patch.object(experimental,"signals",return_value={a:"FLAT" for a in experimental.ARMS})
        self.basic.start()
        self.extra.start()
        self.addCleanup(self.basic.stop)
        self.addCleanup(self.extra.stop)

    def events(self,rows):
        events=[]
        for row in rows:events=f.append(events,row)
        return events

    def test_entry_open_cannot_see_same_day_volume(self):
        first=tick("2026-10-20")
        normal=f.replay(self.events([first,tick("2026-10-21")]),"NASDAQ")
        illiquid=f.replay(self.events([first,tick("2026-10-21",volume=0)]),"NASDAQ")
        self.assertTrue(normal["open_positions"])
        self.assertEqual(normal["open_positions"],illiquid["open_positions"])

    def test_entry_open_cannot_see_same_day_close_or_drawdown(self):
        first=tick("2026-10-20")
        second=tick("2026-10-21")
        normal=f.replay(self.events([first,second,tick("2026-10-22")]),"NASDAQ")
        crash=f.replay(self.events([first,second,tick("2026-10-22",close_factor=.1)]),"NASDAQ")
        self.assertEqual(len(normal["open_positions"]),3)
        self.assertEqual(normal["open_positions"],crash["open_positions"])
        self.assertNotEqual(normal["simulated_equity"],crash["simulated_equity"])

    def test_legacy_replay_keeps_original_policy_and_migration_is_forward_only(self):
        first=tick("2026-10-20",legacy=True)
        second=tick("2026-10-21",volume=0,legacy=True)
        old=f.replay(self.events([first,second]),"NASDAQ")
        self.assertEqual(old["schema"],f.LEGACY_VERSION)
        self.assertFalse(old["open_positions"])
        self.assertEqual(first["schema"],f.LEGACY_VERSION)
        migrated=self.events([first,tick("2026-10-21")])
        self.assertEqual(f.replay(migrated,"NASDAQ")["schema"],f.VERSION)
        with self.assertRaisesRegex(ValueError,"downgrade"):
            f.append(migrated,tick("2026-10-22",legacy=True))

    def test_missed_next_session_does_not_backfill_an_entry(self):
        result=f.replay(self.events([tick("2026-10-20"),tick("2026-10-22")]),"NASDAQ")
        self.assertFalse(result["open_positions"])
        self.assertGreater(result["denials"]["missed_next_session"],0)

    def test_signal_recorded_after_next_open_cannot_fill_that_open(self):
        first=tick("2026-10-20")
        first["observed_at_utc"]="2026-10-21T18:00:00Z"
        result=f.replay(self.events([first,tick("2026-10-21")]),"NASDAQ")
        self.assertFalse(result["open_positions"])
        self.assertGreater(result["denials"]["signal_unavailable_before_open"],0)

    def test_hash_valid_but_semantically_invalid_evidence_is_rejected(self):
        for mutation in ("negative_price","duplicate_date","future_date","nonfinite","expiry"):
            with self.subTest(mutation=mutation):
                row=tick("2026-10-20")
                entry=row["assets"]["AAPL"]
                if mutation=="negative_price":entry["history"][0]["open"]=-1
                elif mutation=="duplicate_date":entry["history"][1]["date"]=entry["history"][0]["date"]
                elif mutation=="future_date":entry["history"][0]["date"]="2026-10-21"
                elif mutation=="nonfinite":entry["history"][0]["volume"]=True
                else:row["membership_expiry"]="2099-12-31"
                entry["history_sha256"]=source.sha(entry["history"])
                with self.assertRaises(ValueError):f.check_snapshot(row)

    def test_replay_rejects_changed_outer_hash(self):
        rows=self.events([tick("2026-10-20")])
        rows[0]["hash"]="f"*64
        with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
            f.replay(rows,"NASDAQ")

    def test_verify_only_rejects_modified_missing_and_stale_outputs_without_writing(self):
        rows=self.events([tick("2026-10-20")])
        report=f.replay(rows,"NASDAQ")
        curve=report.pop("equity_curve")
        with tempfile.TemporaryDirectory() as tmp,patch.object(f,"STATE",Path(tmp)):
            folder=Path(tmp)/"NASDAQ"
            folder.mkdir()
            journal,rep,cur=f.state_paths("NASDAQ")
            journal.write_text(source.canonical(rows[0])+"\n")
            rep.write_text(json.dumps(report))
            cur.write_text(json.dumps(curve))
            before=journal.read_bytes()
            f.verify_saved("NASDAQ")
            changed={**report,"simulated_equity":"999999.00"}
            rep.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,"differs from replay"):
                f.verify_saved("NASDAQ")
            rep.write_text(json.dumps(report))
            cur.write_text("[]")
            with self.assertRaisesRegex(ValueError,"differs from replay"):
                f.verify_saved("NASDAQ")
            cur.unlink()
            with self.assertRaisesRegex(ValueError,"missing derived"):
                f.verify_saved("NASDAQ")
            self.assertEqual(before,journal.read_bytes())

    def test_unpriced_equity_is_unknown_in_economic_audit(self):
        result=economic.equity({"market":"NASDAQ","currency":"USD",
            "closed_trades":0,"initial_capital":"10000",
            "simulated_equity":None,"real_orders":0,"paper_only":True})
        self.assertIsNone(result["return_pct"])
        self.assertFalse(result["valuation_complete"])


class HistoricalEntryVolumeRegression(unittest.TestCase):
    def test_research_and_ensemble_selection_use_only_prior_volume(self):
        # Exactly one signal day; change only the subsequent session's
        # published volume. This must not change the selected OPEN cohort.
        history=bars()
        signal_day=history[130]["date"]
        def signal(rows):
            return {arm:("BUY" if rows[-1]["date"]==signal_day else "FLAT")
                    for arm in (*strategies.ARMS,*experimental.ARMS)}
        def packet(rows):
            return {"market":"NASDAQ","currency":"USD",
                    "is_nontradable_benchmark":False,"history":rows,
                    "history_sha256":source.sha(rows),"corporate_action_dates":{}}
        changed=copy.deepcopy(history)
        changed[131]["volume"]=0
        with patch.object(strategies,"signals",side_effect=signal),patch.object(experimental,"signals",side_effect=signal):
            a=research.evaluate("NASDAQ",{"AAPL":packet(history)})
            b=research.evaluate("NASDAQ",{"AAPL":packet(changed)})
            self.assertGreater(a["per_arm"][strategies.ARMS[0]]["training"]["historical_hypothetical_trades"],0)
            self.assertEqual(a["per_arm"],b["per_arm"])
            a=equity_ensemble.evaluate("NASDAQ",{"AAPL":packet(history)})
            b=equity_ensemble.evaluate("NASDAQ",{"AAPL":packet(changed)})
            self.assertEqual(a,b)


if __name__=="__main__":
    unittest.main()
