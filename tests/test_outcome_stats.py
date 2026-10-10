"""Fixed-horizon research reporting: no SL/TP or mark-to-market."""
import datetime as dt
import unittest
import outcome_stats


UTC=dt.timezone.utc


def row(ident,side,horizon,status="OPEN",pnl=None,late=False,symbol="BTC",strategy="BR-proxy-v1"):
    r={"id":ident,"status":status,"side":side,"symbol":symbol,
       "strategy":strategy,"market_type":"perpetual","horizon_hours":horizon,
       "notional_usd":10000.0,"evaluate_at":"2026-10-08T13:00:00Z"}
    if status=="CLOSED":
        r.update(net_pnl_usd=pnl,normalized_R=pnl/150,
                 late_excluded=late)
    return r


class OutcomeStatsTests(unittest.TestCase):
    def setUp(self):
        self.m=dt.datetime(2026,10,8,12,0,tzinfo=UTC)

    def test_profit_loss_only_after_time_evaluation(self):
        records={
            "A":row("A","LONG",1,status="CLOSED",pnl=90.0),
            "B":row("B","SHORT",2,status="CLOSED",pnl=-110.0),
            "C":row("C","LONG",4),
        }
        result=outcome_stats.summarize(records,self.m)
        self.assertEqual(result["side"]["LONG"]["closed"],1)
        self.assertEqual(result["side"]["LONG"]["active"],1)
        self.assertEqual(result["side"]["LONG"]["wins"],1)
        self.assertEqual(result["side"]["SHORT"]["losses"],1)
        self.assertEqual(result["side"]["SHORT"]["closed_net_usd"],-110)
        self.assertEqual(result["horizon_hours"]["4"]["closed"],0)
        self.assertIsNone(result["horizon_hours"]["4"]["win_rate"])
        self.assertEqual(result["evaluation_next_hour"],1)
        self.assertEqual(result["total_research_notional_usd"],30000)
        self.assertEqual(result["simultaneous_open_research_notional_usd"],10000)
        self.assertIn("NO stop-loss or take-profit",result["exit_policy"])
        self.assertIn("NOT deployable capital",result["exposure_note"])

    def test_due_pending_is_not_closed_or_profit(self):
        pending=row("D","SHORT",1)
        pending["evaluate_at"]="2026-10-08T11:00:00Z"
        result=outcome_stats.summarize([pending],self.m)
        self.assertEqual(result["due_unresolved"],1)
        self.assertEqual(result["side"]["SHORT"]["closed"],0)
        self.assertIsNone(result["side"]["SHORT"]["win_rate"])
        self.assertEqual(result["side"]["SHORT"]["closed_net_usd"],0)

    def test_late_outcome_is_preserved_but_flagged(self):
        records=[row("E","LONG",1,status="CLOSED",pnl=50,late=True)]
        result=outcome_stats.summarize(records,self.m)
        self.assertEqual(result["side"]["LONG"]["late_closes"],1)
        self.assertEqual(result["side"]["LONG"]["timely_closes"],0)
        self.assertEqual(result["eligible_timely_perpetual_closures"],0)

    def test_eligible_cohorts_exclude_late_and_spot_closes(self):
        good=row("G","LONG",2,status="CLOSED",pnl=150)
        late=row("L","LONG",2,status="CLOSED",pnl=999,late=True)
        proxy=row("S","LONG",2,status="CLOSED",pnl=999)
        proxy["market_type"]="spot_proxy"
        r=outcome_stats.summarize([good,late,proxy],self.m)
        x=r["side"]["LONG"]
        self.assertEqual(r["method"],"fixed_horizon_v3")
        self.assertEqual(x["closed"],3)
        self.assertEqual(x["eligible_timely_perpetual_closed"],1)
        self.assertEqual(x["eligible_timely_perpetual_win_rate"],1.0)
        self.assertEqual(x["eligible_timely_perpetual_net_R"],1.0)
        self.assertEqual(x["eligible_timely_perpetual_expectancy_R"],1.0)
        self.assertAlmostEqual(x["eligible_timely_perpetual_share"],1/3,places=4)
        self.assertEqual(r["eligible_timely_perpetual_closures"],1)

    def test_precommitted_regime_daypart_and_day_breadth(self):
        records=[]
        for day, pnl, regime in [(8,150,"24h_up"),(9,-90,"24h_down"),
                                  (10,240,"24h_up")]:
            r=row(str(day),"LONG",8,status="CLOSED",pnl=pnl)
            r["created_at"]=f"2026-10-{day:02d}T14:00:00Z"
            r["regime"]=regime
            records.append(r)
        late=row("late","SHORT",2,status="CLOSED",pnl=500,late=True)
        late["created_at"]="2026-10-09T14:00:00Z"
        late["regime"]="24h_up"
        records.append(late)
        result=outcome_stats.summarize(records,self.m)
        self.assertEqual(result["entry_regime"]["24h_up"]["eligible_timely_perpetual_closed"],2)
        self.assertEqual(result["entry_regime"]["24h_down"]["eligible_timely_perpetual_closed"],1)
        self.assertEqual(result["entry_utc_daypart"]["12-17 UTC"]["closed"],4)
        self.assertEqual(result["entry_utc_daypart"]["12-17 UTC"]["eligible_distinct_entry_utc_days"],3)
        self.assertFalse(result["entry_utc_daypart"]["12-17 UTC"]["eligible_day_breadth_ready"])
        self.assertEqual(result["entry_regime"]["24h_up"]["late_share_of_closed"],round(1/3,4))

    def test_zero_trades_stays_defined(self):
        result=outcome_stats.summarize([],self.m)
        self.assertEqual(result["symbol"],{})
        self.assertEqual(result["entry_regime"],{})
        self.assertEqual(result["entry_utc_daypart"],{})
        self.assertEqual(result["due_unresolved"],0)
        self.assertEqual(result["total_research_notional_usd"],0)


if __name__=="__main__":
    unittest.main()
