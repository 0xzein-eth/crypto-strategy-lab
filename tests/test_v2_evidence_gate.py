"""Multiple-testing research gates are bounded and never route live trades."""
import copy
import datetime as dt
import unittest

from v2 import evidence_gate as gate
from v2.shadow_research import ARMS, VERSION as SHADOW_VERSION
UTC=dt.timezone.utc


def source(rows):
    return {
        "version":SHADOW_VERSION,"catalog_arms":list(ARMS),
        "source_observation_events":45,
        "last_source_hash":"a"*64,
        "closed_outcomes":rows,
    }


def record(arm, day, idx=0,signal=0.20,neutral=-0.10,*,timely=True):
    entered=dt.datetime(2026,1,1,7,0,tzinfo=UTC)+dt.timedelta(
        days=day,minutes=idx*2)
    exit_time=entered+dt.timedelta(hours=4,minutes=6)
    return {
        "arm":arm,
        "entry_id":f"BTC:{arm}:{day}:{idx}",
        "entry_at":entered.isoformat(),
        "entry_day":entered.date().isoformat(),
        "genuine_exit_book_at":exit_time.isoformat(),
        "timely":timely,
        "executable_topbook_quantity_both_sides":True,
        "funding_observed_complete":False,
        "real_exchange_fill":False,
        "symbol":"BTC" if day%2==0 else "ETH",
        "assumed_stressed_net_pct":signal,
        "same_time_neutral_stressed_net_pct":neutral,
        "delta_stress_pct":round(signal-neutral,7),
    }


class SharedDayFamilyWiseGateTests(unittest.TestCase):
    def test_predeclared_26_hypotheses_not_misrepresented_as_proven(self):
        rows=[]
        for day in range(36):
            for ix in range(4):
                rows.append(record("FB-v3",day,ix,signal=.2,neutral=-.1))
                rows.append(record("RSITREND-v1",day,ix,signal=-.2,neutral=.1))
        report=gate.evaluate(source(rows),permutations=256)
        self.assertEqual(report["frozen_familywise_hypotheses"],26)
        self.assertEqual(len(report["arms"]),26)
        self.assertEqual(report["promoted_strategies"],[])
        self.assertFalse(report["real_orders_enabled"])
        positive=report["arms"]["FB-v3"]
        negative=report["arms"]["RSITREND-v1"]
        self.assertEqual(positive["timely_depth_matched_closed"],144)
        self.assertTrue(positive["sufficient_exploratory_calendar_sample"])
        self.assertEqual(positive["distinct_utc_entry_days"],36)
        self.assertGreaterEqual(positive["distinct_iso_weeks"],5)
        self.assertTrue(positive["positive_absolute_stressed_mean_required"])
        self.assertIsNotNone(positive["shared_day_maxT_adjusted_p_exploratory"])
        self.assertTrue(0 < positive["shared_day_maxT_adjusted_p_exploratory"]<=1)
        self.assertEqual(negative["positive_day_level_statistic"],0)
        self.assertFalse(negative["positive_absolute_stressed_mean_required"])
        self.assertFalse(positive["eligible_for_live_or_auto_promotion"])
        self.assertFalse(positive["untouched_final_validation"])
        self.assertTrue(report["funding_unknown_blocks_deployment"])

    def test_13_calendar_days_cannot_become_significant_just_with_many_trades(self):
        rows=[record("FB-v3",day,ix) for day in range(13)
              for ix in range(40)]
        report=gate.evaluate(source(rows),permutations=256)
        assert report["arms"]["FB-v3"]["timely_depth_matched_closed"]==520
        self.assertFalse(report["arms"]["FB-v3"]["sufficient_exploratory_calendar_sample"])
        self.assertIsNone(report["arms"]["FB-v3"]["shared_day_maxT_adjusted_p_exploratory"])
        self.assertEqual(report["arms"]["FB-v3"]["positive_day_level_statistic"],0)

    def test_exit_asof_cutoff_severs_future_outcomes_not_retroactive_entry(self):
        rows=[record("FB-v3",day,i) for day in range(24) for i in range(5)]
        later=record("FB-v3",42,1,signal=9,neutral=-9)
        ref=gate.evaluate(source(rows),permutations=256)
        cutoff="2026-01-30T00:00:00Z"
        a=gate.evaluate(source([*rows,later]),asof=cutoff,permutations=256)
        b=gate.evaluate(source(rows),asof=cutoff,permutations=256)
        self.assertEqual(a["arms"],b["arms"])
        self.assertEqual(a["excluded_closed_outcomes_after_asof"],1)
        self.assertEqual(ref["arms"],b["arms"])

    def test_malformed_or_duplicated_pairs_are_never_counted(self):
        base=record("FB-v3",0)
        with self.assertRaisesRegex(ValueError,"duplicate"):
            gate.evaluate(source([base,copy.deepcopy(base)]),permutations=256)
        bad=copy.deepcopy(base)
        bad["delta_stress_pct"]=999
        with self.assertRaisesRegex(ValueError,"counterpart mismatch"):
            gate.evaluate(source([bad]),permutations=256)
        bad=copy.deepcopy(base)
        bad["funding_observed_complete"]=True
        with self.assertRaisesRegex(ValueError,"funding"):
            gate.evaluate(source([bad]),permutations=256)
        with self.assertRaisesRegex(ValueError,"catalog"):
            gate.evaluate({**source([]),"catalog_arms":["FB-v3"]},permutations=256)
        with self.assertRaisesRegex(ValueError,"bounded"):
            gate.evaluate(source([]),permutations=4)

    def test_shuffled_input_cannot_change_frozen_results(self):
        rows=[record("FB-v3",day,ix) for day in range(26) for ix in range(4)]
        a=gate.evaluate(source(rows),permutations=256)
        b=gate.evaluate(source(list(reversed(rows))),permutations=256)
        self.assertEqual(a["arms"],b["arms"])
        self.assertTrue(a["common_utc_day_null_flips"])
        self.assertFalse(any(v["eligible_for_live_or_auto_promotion"]
                             for v in a["arms"].values()))


if __name__=="__main__":
    unittest.main()
