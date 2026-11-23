"""Leakage and temporal-split tests for the supervised research dataset."""
import datetime as dt
import unittest

import dataset_builder

UTC = dt.timezone.utc


def record(day=1, *, status="CLOSED", market_type="perpetual",
           late=False, target=0.2, symbol="BTC"):
    opened = dt.datetime(2026, 10, day, 0, 0, tzinfo=UTC)
    due = opened + dt.timedelta(hours=4)
    closed = due + dt.timedelta(minutes=1)
    evidence = {
        "bar_span": "15m confirmed OKX USDT-SWAP",
        "last_close": 100.0, "last_open": 99.0, "last_high": 102.0,
        "last_low": 98.0, "sma20": 99.0, "sma50": 98.0,
        "sma20prev": 98.5, "sma50prev": 97.5, "rsi14": 60.0,
        "rsi14prev": 55.0, "z20": 0.5, "atr14": 2.0,
        "prev_high20": 101.0, "prev_low20": 95.0, "vol_ratio": 1.2,
        "prior20_range_width": 10.0, "older20_range_width": 12.0,
        "prior20_mean_range": 2.0, "upper_wick_ratio": 0.2,
        "lower_wick_ratio": 0.3, "vwap20": 99.0,
    }
    return {
        "id": f"LAB-{day}", "status": status, "market_type": market_type,
        "late_excluded": late, "provider": "okx-swap", "horizon_hours": 4,
        "created_at": opened.isoformat().replace("+00:00", "Z"),
        "evaluate_at": due.isoformat().replace("+00:00", "Z"),
        "exit_observed_at": closed.isoformat().replace("+00:00", "Z"),
        "resolved_at": closed.isoformat().replace("+00:00", "Z"),
        "evidence": evidence, "regime": "24h_up", "side": "LONG",
        "symbol": symbol, "strategy": "FB-v3",
        "normalized_R": target, "research_risk_pct": 1.5,
        "net_pnl_usd": 1.0,
    }


class DatasetBuilderTests(unittest.TestCase):
    def test_only_timely_closed_perpetual_confirmed_rows_are_included(self):
        rows = [
            record(1), record(2, market_type="spot_proxy"),
            record(3, late=True), record(4, status="OPEN"),
        ]
        dataset = dataset_builder.build_dataset(rows)
        self.assertEqual(dataset["eligible_examples"], 1)
        self.assertEqual(dataset["excluded_records"], 3)
        self.assertTrue(dataset["features_are_open_time_only"])
        self.assertEqual(dataset["examples"][0]["label"], 1)

    def test_features_do_not_depend_on_close_outcome(self):
        a = record(1, target=0.2)
        b = record(1, target=-0.8)
        self.assertEqual(dataset_builder.feature_values(a),
                         dataset_builder.feature_values(b))
        da = dataset_builder.build_dataset([a])["examples"][0]
        db = dataset_builder.build_dataset([b])["examples"][0]
        self.assertNotEqual(da["label"], db["label"])
        self.assertNotIn("net_pnl_usd", da["features"])
        self.assertNotIn("normalized_R", da["features"])

    def test_chronological_split_purges_embargo_and_reports_non_pristine_validation(self):
        examples = []
        for day in range(1, 11):
            row = record(day)
            examples.append({
                "record_id": row["id"], "entry_at": row["created_at"],
                "label_available_at": row["resolved_at"],
                "features": {}, "label": day % 2, "target_r": 0.1,
            })
        split = dataset_builder.chronological_split(
            {"examples": examples}, validation_fraction=0.2, embargo_hours=24)
        self.assertGreater(len(split["train"]), 0)
        self.assertGreater(len(split["validation"]), 0)
        self.assertGreater(split["purged_training_rows"], 0)
        self.assertFalse(split["validation_is_pristine_holdout"])
        self.assertTrue(split["future_prospective_holdout_required"])


if __name__ == "__main__":
    unittest.main()
