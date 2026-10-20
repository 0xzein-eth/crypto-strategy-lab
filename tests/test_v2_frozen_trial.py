"""Frozen future trial must NOT peek, optimize, or enable live orders."""
import copy
import datetime as dt
import unittest

from v2 import frozen_trial as trial
from v2 import forward_paper as f
from v2 import shadow_research as shadow

UTC=dt.timezone.utc
H="f"*64


def wallet(at):
    return {"version":f.VERSION,"last_tick_hash":H,
            "latest_real_observation_utc":at.isoformat().replace("+00:00","Z"),
            "real_order_submissions":0,
            "funding_source_complete":False,
            "future_slippage_and_market_impact_unverified":True,
            "closed_positions":0,
            "observed_max_drawdown_usdt":"0.00",
            "observed_closed_profit_factor_fee_bidask_only":None}


def source(rows=()):
    return {"version":shadow.VERSION,"last_source_hash":H,
            "real_order_submissions":0,
            "catalog_arms":list(shadow.ARMS),"closed_outcomes":list(rows),
            "source_observation_events":100}


class FrozenProspectiveContractTests(unittest.TestCase):
    def test_policy_exact_start_end_and_zero_orders(self):
        c=trial.contract()
        self.assertEqual(c["schema"],trial.VERSION)
        self.assertEqual(c["future_entry_start_utc"],"2026-10-21T00:00:00+00:00")
        self.assertEqual(c["future_entry_end_exclusive_utc"],"2027-01-19T00:00:00+00:00")
        self.assertEqual((trial.END-trial.START).days,90)
        self.assertEqual(c["frozen_catalog_count"],26)
        self.assertEqual(c["predeclared_candidate_arms"],["FB-v3","VWAP-v1"])
        self.assertEqual(len(c["frozen_policy_digest_sha256"]),64)
        self.assertTrue(c["requires_explicit_separate_user_approval_for_any_real_execution"])
        self.assertEqual(c,trial.contract())

    def test_before_registration_starts_no_future_results_or_prediction(self):
        out=trial.evaluate(wallet(dt.datetime(2026,10,20,4,tzinfo=UTC)),source())
        self.assertEqual(out["phase"],"WAITING_FOR_FUTURE_REGISTRATION_START")
        self.assertTrue(out["results_withheld"])
        self.assertFalse(out["deployment_authorized"])
        self.assertNotIn("per_candidate_descriptive_review",out)

    def test_during_collection_even_strong_winners_remain_blinded(self):
        now=trial.START+dt.timedelta(days=7)
        entry=trial.START+dt.timedelta(days=1)
        outcome={
            "entry_id":"BTC:FB-v3:future-synthetic",
            "entry_at":entry.isoformat(),"genuine_exit_book_at":(
                entry+dt.timedelta(hours=4)).isoformat(),
        }
        data=source([outcome])
        obs=trial.evaluate(wallet(now),data)
        self.assertEqual(obs["phase"],"COLLECTING_PREDECLARED_FUTURE")
        self.assertTrue(obs["results_withheld"])
        self.assertEqual(obs["actual_observed_validity_subset_count"],1)
        self.assertNotIn("per_candidate_descriptive_review",obs)
        self.assertNotIn("both_candidates_positive_exploratory_maxT",obs)
        self.assertFalse(obs["alpha_proven"])
        self.assertFalse(obs["deployment_authorized"])

    def test_source_alignment_and_future_clock_guards(self):
        at=trial.START+dt.timedelta(days=2)
        with self.assertRaisesRegex(ValueError,"diverged"):
            trial.evaluate(wallet(at),{**source(),"last_source_hash":"1"*64})
        with self.assertRaisesRegex(ValueError,"actual trading"):
            trial.evaluate({**wallet(at),"real_order_submissions":1},source())
        with self.assertRaisesRegex(ValueError,"cannot claim future"):
            trial.evaluate(wallet(at),source(),now=trial.START)
        with self.assertRaisesRegex(ValueError,"mismatching"):
            trial.evaluate(wallet(at),{**source(),"version":"tampered"})

    def test_calendar_end_does_not_prove_alpha_or_funding(self):
        after=trial.END+dt.timedelta(minutes=35)
        status=trial.evaluate(wallet(after),source())
        self.assertEqual(status["phase"],
                         "FINAL_WINDOW_ENDED_UNVERIFIED_EXECUTION_AND_REVIEW_REQUIRED")
        self.assertFalse(status["results_withheld"])
        self.assertFalse(status["maturity_reached"])
        self.assertFalse(status["complete_funding_spread_slippage_impact"])
        self.assertFalse(status["cash_constrained_hypothetical_wallet_risk_gate"])
        self.assertFalse(status["deployment_authorized"])
        self.assertFalse(status["after_all_costs_untouched_alpha_proven"])
        self.assertEqual(len(status["per_candidate_descriptive_review"]),2)
        self.assertIn("UNMEASURED_FUNDING_OR_ACTUAL_EXECUTION",
                      status["final_readiness_blockers"])

    def test_outside_window_labels_do_not_inflate_trial(self):
        now=trial.START+dt.timedelta(days=8)
        outside={
            "entry_id":"BTC:FB-v3:before-policy-synthetic",
            "entry_at":(trial.START-dt.timedelta(hours=1)).isoformat(),
            "genuine_exit_book_at":(trial.START+dt.timedelta(hours=3)).isoformat(),
        }
        status=trial.evaluate(wallet(now),source([outside]))
        self.assertEqual(status["actual_observed_validity_subset_count"],0)


if __name__=="__main__":
    unittest.main()
