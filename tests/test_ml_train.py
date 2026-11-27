import datetime as dt
import unittest
import ml_train


def sample(day, ident, horizon=4, label=1, strategy="FB-v3"):
    stamp = "2026-01-%02dT00:00:00Z" % day
    return {"sample_id": ident, "entry_at": stamp, "features_asof": stamp,
            "features": {"horizon_hours": horizon, "price_change_24h_pct": 1.0,
                         "quote_volume_24h": 1000.0, "strategy": strategy,
                         "side": "LONG", "symbol": "BTC", "regime": "24h_up",
                         "cluster": "CRYPTO_BETA", "provider": "okx-swap"},
            "labels": {"net_profit": label}}


class LogisticBaselineTests(unittest.TestCase):
    def test_gradient_descent_learns_separable_signal(self):
        matrix = [[1.0, -1.0], [1.0, -0.5], [1.0, 0.5], [1.0, 1.0]]
        weights = ml_train.fit_logistic(matrix, [0, 0, 1, 1], epochs=1500)
        probabilities = ml_train.predict(matrix, weights)
        self.assertLess(probabilities[0], probabilities[-1])
        self.assertLess(probabilities[1], probabilities[2])

    def test_sparse_optimizer_matches_dense_gradient_descent(self):
        matrix = [[1.0, 0.0, -1.0, 0.0], [1.0, 2.0, 0.0, 1.0],
                  [1.0, 0.0, 1.0, 0.0], [1.0, -2.0, 0.0, 1.0]]
        labels = [0, 1, 1, 0]
        expected = [0.0] * 4
        for _ in range(30):
            gradient = [0.0] * 4
            for row, target in zip(matrix, labels):
                error = ml_train.sigmoid(sum(w*x for w, x in zip(expected, row))) - target
                for j, value in enumerate(row):
                    gradient[j] += error * value
            for j in range(4):
                gradient[j] = gradient[j]/len(labels) + (0.01*expected[j] if j else 0.0)
                expected[j] -= 0.05 * gradient[j]
        actual = ml_train.fit_logistic(matrix, labels, epochs=30)
        for left, right in zip(actual, expected):
            self.assertAlmostEqual(left, right, places=12)

    def test_time_split_is_ordered_and_purged(self):
        rows = [sample(day, str(day)) for day in range(1, 29)]
        train, validation, test = ml_train.split_chronologically(rows, 24.5)
        train_end = ml_train.parse_time(train[-1]["entry_at"])
        valid_start = ml_train.parse_time(validation[0]["entry_at"])
        valid_end = ml_train.parse_time(validation[-1]["entry_at"])
        test_start = ml_train.parse_time(test[0]["entry_at"])
        self.assertGreaterEqual((valid_start-train_end).total_seconds(), 24.5*3600)
        self.assertGreaterEqual((test_start-valid_end).total_seconds(), 24*3600)


    def test_default_purge_covers_24h_horizon_plus_30m_observation_delay(self):
        rows = [sample(day, str(day)) for day in range(1, 29)]
        train, validation, test = ml_train.split_chronologically(rows)
        train_end = ml_train.parse_time(train[-1]["entry_at"])
        valid_start = ml_train.parse_time(validation[0]["entry_at"])
        self.assertGreaterEqual((valid_start-train_end).total_seconds(), 24.5*3600)

    def test_unknown_categories_and_missing_numeric_are_handled(self):
        train = [sample(day, str(day), label=day % 2) for day in range(1, 5)]
        schema = ml_train.encode_fit(train)
        unseen = sample(5, "unseen", strategy="new-strategy")
        unseen["features"]["price_change_24h_pct"] = None
        vector = ml_train.encode(unseen, schema)
        self.assertEqual(len(vector), len(schema["columns"]))
        self.assertTrue(all(value == value for value in vector))

    def test_no_rows_are_promoted(self):
        result = ml_train.run([])
        self.assertEqual(result["trained_horizons"], 0)
        self.assertEqual(result["promotion"], "PROHIBITED_SHADOW_ONLY")


if __name__ == "__main__":
    unittest.main()
