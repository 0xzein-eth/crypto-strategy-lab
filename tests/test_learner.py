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
        self.assertIsNone(p["champion"])
        self.assertIn("BR-v3",p["provisional_leaders"])
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

    def test_train_only_persistent_losses_reduce_weight_without_erasure(self):
        days=[(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat()
              for i in range(100)]
        rows=[]
        for d in days:
            for _ in range(3):
                rows.extend((trade("CTRL-v1",d,0.0),
                             trade("BR-proxy-v1",d,-1.0),
                             trade("MR-proxy-v1",d,0.2)))
        profile=learner.analysis(rows)
        self.assertIn("BR-proxy-v1",profile["training_only_underperformers"])
        self.assertNotIn("CTRL-v1",profile["training_only_underperformers"])
        self.assertNotIn("MR-proxy-v1",profile["training_only_underperformers"])
        controls=[{"strategy":"CTRL-v1","side":"LONG"},
                  {"strategy":"BR-proxy-v1","side":"LONG"},
                  {"strategy":"MR-proxy-v1","side":"SHORT"}]
        selected=[learner.choose(controls,rows,"BTC",4,k,0,profile)
                  for k in range(1500)]
        br=sum(p["strategy"]=="BR-proxy-v1" for p,_ in selected)
        mr=sum(p["strategy"]=="MR-proxy-v1" for p,_ in selected)
        ctrl=sum(p["strategy"]=="CTRL-v1" for p,_ in selected)
        self.assertGreater(br,0)
        self.assertLess(abs(mr-br),250)
        self.assertGreaterEqual(ctrl,240)
        self.assertTrue(all("neutral_exploration" in mode or mode=="control_exploration"
                            for _,mode in selected))
        # A different MONITORING outcome cannot influence next-round choices.
        changed=[dict(x) for x in rows]
        for x in changed:
            if x["strategy"]=="BR-proxy-v1" and learner.stable_bucket(
                    "holdout:"+learner.day_of(x),5)==0:
                x["normalized_R"]=3.0
        p2=learner.analysis(changed)
        self.assertEqual(profile["training_only_underperformers"],
                         p2["training_only_underperformers"])
        self.assertEqual(
            selected,
            [learner.choose(controls,changed,"BTC",4,k,0,p2)
             for k in range(1500)])

    def test_training_ranks_never_prioritize_before_independent_validation(self):
        choices=[{"strategy":"BR-proxy-v1","side":"LONG"},
                 {"strategy":"MR-proxy-v1","side":"SHORT"},
                 {"strategy":"CTRL-v1","side":"LONG"}]
        leading={"allocation_leaders":["BR-proxy-v1"],
                 "training_only_underperformers":["MR-proxy-v1"]}
        reversed_leading={"allocation_leaders":["MR-proxy-v1"],
                          "training_only_underperformers":["BR-proxy-v1"]}
        for slot in range(200):
            one=learner.choose(choices,[],"BTC",4,slot,0,profile=leading)
            two=learner.choose(choices,[],"BTC",4,slot,0,profile=reversed_leading)
            self.assertEqual(one,two)
            self.assertNotIn(one[1],("train_only_exploratory_allocation",
                                    "training_underperformer_downweighted"))

    def test_few_days_cannot_downweight_even_large_negative_sample(self):
        rows=[]
        for i in range(3):
            day=(dt.date(2026,2,1)+dt.timedelta(days=i)).isoformat()
            rows.extend([trade("BR-proxy-v1",day,-3)]*500)
            rows.extend([trade("CTRL-v1",day,0)]*500)
        p=learner.analysis(rows)
        self.assertEqual(p["training_only_underperformers"],[])
        self.assertFalse(p["arms"]["BR-proxy-v1"]["underperformer_train_only"])

    def test_source_quality_sampling_preserves_ctrl_and_proxy_exploration(self):
        # This is a preregistered input-quality split, not a policy that
        # silently reallocates toward recent lucky or winning strategies.
        options=[{"strategy":"CTRL-v1","side":"LONG"},
                 {"strategy":"BR-proxy-v1","side":"LONG"},
                 {"strategy":"MR-proxy-v1","side":"SHORT"},
                 {"strategy":"IBREAK-v1","side":"LONG"},
                 {"strategy":"BANDREV-v1","side":"SHORT"},
                 {"strategy":"EFFTREND-v1","side":"LONG"},
                 {"strategy":"VWAPTR-v1","side":"SHORT"}]
        counts={"IBREAK-v1":1,"BANDREV-v1":4,
                "EFFTREND-v1":8,"VWAPTR-v1":3}
        profile={"entry_exposure_counts_v1":counts}
        candidates=[learner.choose(options,[],"BTC",4,k,0,profile)
                    for k in range(5000)]
        ctrl=sum(x["strategy"]=="CTRL-v1" for x,_ in candidates)
        advanced=sum(x["strategy"] in learner.ADVANCED for x,_ in candidates)
        proxy=sum(x["strategy"] in learner.BASELINES[:2] for x,_ in candidates)
        srcbalanced=sum(mode=="confirmed_entry_coverage_neutral_exploration"
                        for _,mode in candidates)
        self.assertGreaterEqual(ctrl,850)
        self.assertLess(ctrl,1450)
        self.assertGreaterEqual(advanced,3000)
        self.assertLess(proxy,700)
        self.assertGreater(proxy,75)
        self.assertGreater(srcbalanced,1400)
        self.assertEqual(candidates,[learner.choose(options,[],"BTC",4,k,0,profile)
                                      for k in range(5000)])
        # Outcomes/monitoring don't enter choices. Newer candidates appear
        # only if the REAL confirmed signals pipeline offered them.
        pretend_winner=dict(profile,allocation_leaders=["VWAPTR-v1"],
                             provisional_leaders=["BR-proxy-v1"],
                             champion="BANDREV-v1")
        self.assertEqual(candidates,
                         [learner.choose(options,[],"BTC",4,k,0,pretend_winner)
                          for k in range(5000)])
        baselines=[x for x in options if x["strategy"] in learner.BASELINES]
        self.assertTrue(all(learner.choose(baselines,[],"BTC",4,k,0,profile)[0]
                            in baselines for k in range(50)))

    def test_unconfirmed_advanced_never_selected(self):
        options=[{"strategy":"BR-proxy-v1","side":"SHORT"},
                 {"strategy":"MR-proxy-v1","side":"LONG"},
                 {"strategy":"CTRL-v1","side":"LONG"}]
        for slot in range(100):
            selected,_=learner.choose(options,[],"SOL",8,slot,4)
            self.assertIn(selected,options)


if __name__=="__main__":
    unittest.main()
