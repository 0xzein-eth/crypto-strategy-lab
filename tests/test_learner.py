import datetime as dt
import unittest

import learner


def trade(arm,day,r_value,market_type="perpetual",late=False,horizon=2):
    return {
        "strategy":arm,
        "created_at":day+"T03:00:00Z",
        "status":"CLOSED",
        "market_type":market_type,
        "late_excluded":late,
        "normalized_R":r_value,
        "horizon_hours":horizon,
    }


class LearningTests(unittest.TestCase):
    def test_exclusion_is_strict(self):
        rows=[
            trade("BR-v3","2026-10-01",5,market_type="spot_proxy"),
            trade("BR-v3","2026-10-01",6,late=True),
            trade("BR-v3","2026-10-01",1),
            dict(trade("BR-v3","2026-10-01",1),status="OPEN"),
        ]
        p=learner.analysis(rows)
        self.assertEqual(p["eligible_closed"],1)
        self.assertEqual(p["arms"]["BR-v3"]["n"],1)
        self.assertIsNone(p["champion"])

    def test_holdout_days_never_leak_to_training(self):
        dates=[(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat() for i in range(60)]
        rows=[trade("BR-v3",date,1.0) for date in dates]
        s=learner.analysis(rows)["arms"]["BR-v3"]
        self.assertEqual(s["train_n"]+s["holdout_n"],60)
        self.assertEqual(s["train_days"]+s["holdout_days"],60)
        self.assertFalse(s["preferential"]) # no control group yet

    def test_control_and_holdout_required_for_provisional_leader(self):
        dates=[(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat() for i in range(100)]
        rows=[]
        for date in dates:
            for n in range(2):
                rows.append(trade("BR-v3",date,1.0))
                rows.append(trade("CTRL-v1",date,-0.1))
        p=learner.analysis(rows)
        self.assertEqual(p["champion"],"BR-v3")
        self.assertTrue(p["arms"]["BR-v3"]["preferential"])
        for r in rows:
            if r["strategy"]=="BR-v3" and learner.stable_bucket("holdout:"+learner.day_of(r),5)==0:
                r["normalized_R"]=-1.0
        p2=learner.analysis(rows)
        self.assertIsNone(p2["champion"])
        self.assertLess(p2["arms"]["BR-v3"]["holdout_net_R"],0)

    def test_monitoring_outcomes_never_change_allocation(self):
        # A monitoring result can change the displayed candidate, but must
        # NEVER alter next-run selections. Only training evidence may do that.
        dates=[(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat() for i in range(100)]
        rows=[]
        for day in dates:
            for _ in range(2):
                rows.append(trade("BR-v3",day,1.0))
                rows.append(trade("CTRL-v1",day,-0.1))
        stressed=[dict(x) for x in rows]
        for x in stressed:
            if x["strategy"]=="BR-v3" and learner.stable_bucket(
                    "holdout:"+learner.day_of(x),5)==0:
                x["normalized_R"]=-2.0
        good=learner.analysis(rows)
        bad=learner.analysis(stressed)
        self.assertNotEqual(good["provisional_leaders"],bad["provisional_leaders"])
        self.assertEqual(good["allocation_leaders"],bad["allocation_leaders"])
        self.assertIn("BR-v3",good["allocation_leaders"])
        options=[{"strategy":"BR-v3","side":"LONG"},
                 {"strategy":"CTRL-v1","side":"SHORT"}]
        for slot in range(120):
            args=("BTC",2,slot,0)
            self.assertEqual(
                learner.choose(options,rows,*args,profile=good),
                learner.choose(options,stressed,*args,profile=bad))

    def test_allocations_deterministic_and_control_preserved(self):
        options=[
            {"strategy":"BR-proxy-v1","side":"LONG"},
            {"strategy":"MR-proxy-v1","side":"SHORT"},
            {"strategy":"CTRL-v1","side":"LONG"},
        ]
        picks=[learner.choose(options,[],"BTC",4,slot,0) for slot in range(200)]
        self.assertEqual(picks,[learner.choose(options,[],"BTC",4,slot,0) for slot in range(200)])
        self.assertGreater(sum(p[0]["strategy"]=="CTRL-v1" for p in picks),20)
        self.assertGreater(sum(p[0]["strategy"]!="CTRL-v1" for p in picks),60)
        self.assertTrue(all(p[1]!="provisional_leader_allocation" for p in picks))

    def test_unconfirmed_advanced_never_selected(self):
        options=[{"strategy":"BR-proxy-v1","side":"SHORT"},
                 {"strategy":"MR-proxy-v1","side":"LONG"},
                 {"strategy":"CTRL-v1","side":"LONG"}]
        for slot in range(100):
            selected,_=learner.choose(options,[],"SOL",8,slot,4)
            self.assertIn(selected,options)


if __name__=="__main__":
    unittest.main()
