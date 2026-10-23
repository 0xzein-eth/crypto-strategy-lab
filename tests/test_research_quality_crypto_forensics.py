import unittest
from research_quality.crypto_forensics import analyze, score

def closed(ident, pnl, date):
    return {"id":ident,"status":"CLOSED","net_pnl_usd":pnl,
            "fee_round_trip_usd":10,"notional_usd":10000,
            "created_at":date,"strategy":"S","horizon_hours":4,
            "market_type":"perpetual","late_excluded":False}

def baseline(rows):
    return {"schema_version":8,"created":len(rows),"closed":len(rows),
            "net_pnl_usd":round(sum(x["net_pnl_usd"] for x in rows),2),
            "total_round_trip_fees_usd":10*len(rows),"timestamp":"2026-10-23T00:00:00Z",
            "verified_events":len(rows)*2,"ledger_tip_sha256":"a"*64}

class CryptoForensicsTests(unittest.TestCase):
    def test_reconciliation(self):
        rows=[closed("1",-15,"2026-10-20T00:00:00Z"),
              closed("2",5,"2026-10-21T00:00:00Z")]
        o=analyze(rows,baseline(rows))
        self.assertEqual(o["all_closed"]["net_usd"],-10)
        self.assertEqual(o["all_closed"]["gross_price_pnl_usd"],10)
        self.assertEqual(o["all_closed"]["distinct_utc_entry_days"],2)
        self.assertEqual(o["champion"],None)
    def test_report_mismatch_is_fatal(self):
        rows=[closed("1",-15,"2026-10-20T00:00:00Z")]
        report=baseline(rows)
        report["net_pnl_usd"]=999
        with self.assertRaises(ValueError):
            analyze(rows,report)
    def test_same_day_correlated(self):
        rows=[closed("1",-10,"2026-10-20T00:00:00Z"),
              closed("2",-10,"2026-10-20T03:00:00Z")]
        self.assertEqual(score(rows)["distinct_utc_entry_days"],1)
    def test_negative_fee_rejected(self):
        row=closed("1",3,"2026-10-20T00:00:00Z")
        row["fee_round_trip_usd"]=-1
        with self.assertRaises(ValueError):
            score([row])
