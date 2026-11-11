"""Synthetic fixtures only: never written into actual observation state."""
import copy
import datetime as dt
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from adaptive_lab import registry, policy, source, engine, history
from research_v9.factory import Features

UTC=dt.timezone.utc
EPOCH=int(dt.datetime(2026,1,1,tzinfo=UTC).timestamp()*1000)
STRATEGY=registry.catalog()[0].id


def outcomes(blocks=3,values=None,strategy=STRATEGY,lane="EXPLORATION"):
    rows=[]
    for block in range(blocks):
        value=values[block] if values else .8
        for i in range(40):
            entry=EPOCH+block*policy.BLOCK_MS+(i%10+1)*policy.DAY_MS+i*1000
            rows.append({"id":f"{strategy}:{lane}:{block}:{i}","strategy":strategy,
                "symbol":"BTC" if i%2 else "ETH","lane":lane,"eligible":True,
                "entry_ms":entry,"exit_ms":entry+3600000,
                "stress_pct":value+i*.0001,"delta_pct":value/2+i*.00001})
    return rows


def asset(symbol,now,*,price=100,size="10"):
    end=int(now.timestamp()*1000)//900000*900000
    bars=[[end-(128-i)*900000,100,101,99,100,10000] for i in range(128)]
    funding_end=int(now.timestamp()*1000)//28800000*28800000
    return {"book":{"provider":"okx-swap","market_type":"perpetual",
        "symbol":symbol,"instrument":symbol+"-USDT-SWAP","bid":str(price),
        "ask":str(price+.01),"bid_size_base":size,"ask_size_base":size,
        "observed_at":source.iso(now)},"candles":bars,
        "funding":[[funding_end-i*28800000,.0001] for i in reversed(range(5))],
        "contract_base_value":".01","real_orders":0}


def tick(now,*,price=100,size="10"):
    return {"observed_at":source.iso(now),"assets":{
        symbol:asset(symbol,now,price=price,size=size) for symbol in ("BTC","ETH")},
        "source_failures":{},"symbols_requested":["BTC","ETH"],
        "public_sources_only":True,"real_orders":0}


class TierTests(unittest.TestCase):
    def classify(self,rows,k=3,previous=None):
        return policy.classify(rows,epoch_ms=EPOCH,checkpoint=k,previous=previous)[STRATEGY]

    def test_three_positive_independent_blocks_become_high_but_never_live(self):
        result=self.classify(outcomes())
        self.assertEqual(result["tier"],"HIGH")
        self.assertFalse(result["candidate_for_human_review"])
        self.assertFalse(result["live_orders_authorized"])
        self.assertLess(result["holm_day_sign_p"],result["checkpoint_alpha"])

    def test_negative_and_inconsistent_blocks_have_distinct_tiers(self):
        self.assertEqual(self.classify(outcomes(values=[-1,-1,-1]))["tier"],"LOW")
        self.assertEqual(self.classify(outcomes(values=[1,-1,1]))["tier"],"MEDIUM")

    def test_same_checkpoint_does_not_count_as_new_retest(self):
        rows=outcomes()
        first=self.classify(rows)
        second=self.classify(rows,previous={STRATEGY:first})
        self.assertEqual(first,second)
        self.assertEqual(second["positive_block_streak"],3)

    def test_not_enough_samples_or_distinct_days_remains_warmup(self):
        rows=outcomes()
        self.assertEqual(self.classify(rows[:99])["tier"],"WARMUP")
        for row in rows:
            block=(row["entry_ms"]-EPOCH)//policy.BLOCK_MS
            row["entry_ms"]=EPOCH+block*policy.BLOCK_MS+policy.DAY_MS
            row["exit_ms"]=row["entry_ms"]+3600000
        self.assertEqual(self.classify(rows)["tier"],"WARMUP")

    def test_priority_lane_does_not_inflate_evidence(self):
        self.assertEqual(self.classify(outcomes(lane="PRIORITY"))["tier"],"WARMUP")
        rows=outcomes()
        self.assertEqual(self.classify(rows),self.classify(rows+outcomes(lane="PRIORITY")))

    def test_future_closes_unknown_costs_and_cross_block_trades_do_not_qualify(self):
        for condition in ("future","unknown","cross"):
            rows=outcomes()
            for row in rows:
                if condition=="future":row["exit_ms"]=EPOCH+4*policy.BLOCK_MS
                elif condition=="unknown":row["eligible"]=False;row["stress_pct"]=None
                else:
                    block=(row["entry_ms"]-EPOCH)//policy.BLOCK_MS
                    row["exit_ms"]=EPOCH+(block+1)*policy.BLOCK_MS+1
            self.assertEqual(self.classify(rows)["tier"],"WARMUP")

    def test_duplicate_or_nonfinite_results_fail_closed(self):
        rows=outcomes()
        with self.assertRaisesRegex(ValueError,"duplicate"):self.classify(rows+[rows[0]])
        rows[0]["stress_pct"]=float("nan")
        with self.assertRaisesRegex(ValueError,"nonfinite"):self.classify(rows)

    def test_five_blocks_required_before_candidate_review(self):
        result=self.classify(outcomes(blocks=5),k=5)
        self.assertEqual(result["tier"],"HIGH")
        self.assertTrue(result["candidate_for_human_review"])
        self.assertEqual(result["positive_block_streak"],5)

    def test_low_review_uses_elapsed_calendar_days(self):
        previous=None
        for k in (3,4,5):
            all_states=policy.classify(outcomes(blocks=k,values=[-1]*k),
                epoch_ms=EPOCH,checkpoint=k,previous=previous)
            previous=all_states
            self.assertEqual(all_states[STRATEGY]["needs_redevelopment"],k>=5)

    def test_family_correction_includes_every_registered_hypothesis(self):
        corrected=policy.holm({"a":.001,"b":1,"c":1})
        self.assertEqual(corrected["a"],.003)
        self.assertAlmostEqual(sum(.05/(k*(k+1)) for k in range(1,10000)),.05,places=4)


class RegistryAllocationTests(unittest.TestCase):
    def test_bounded_unique_catalog_and_children_have_new_identity(self):
        rows=registry.catalog()
        self.assertEqual(len(rows),174)
        self.assertEqual(len({h.id for h in rows}),174)
        self.assertEqual(sum(bool(h.parents) for h in rows),30)
        self.assertTrue(all(len(h.parents)==3 for h in rows if h.parents))

    def test_all_signals_are_asof_and_children_require_activation(self):
        now=dt.datetime(2026,1,1,10,1,tzinfo=UTC)
        bars=asset("BTC",now)["candles"]
        future=copy.deepcopy(bars[-1])
        future[0]+=900000
        future[1:5]=[1000,1001,999,1000]
        self.assertEqual(registry.votes_at(Features(bars),127),
                         registry.votes_at(Features(bars+[future]),127))
        self.assertFalse(any("_mix" in key for key in registry.proposals(bars)))

    def candidates(self):
        return [{"strategy":f"strategy{i}","symbol":registry.SYMBOLS[i%16],
                 "family":f"family{i%12}"} for i in range(96)]

    def test_uniform_lane_is_tier_independent_and_budget_is_bounded(self):
        candidates=self.candidates()
        low={c["strategy"]:{"tier":"LOW"} for c in candidates}
        high={c["strategy"]:{"tier":"HIGH"} for c in candidates}
        a=policy.select(candidates,low,slot=32)
        b=policy.select(candidates,high,slot=32)
        self.assertEqual([c for c in a if c["lane"]=="EXPLORATION"],
                         [c for c in b if c["lane"]=="EXPLORATION"])
        self.assertEqual(sum(c["lane"]=="EXPLORATION" for c in a),8)
        self.assertEqual(len(a),32)

    def test_cadence_gives_high_extra_tests_between_low_ticks(self):
        candidates=self.candidates()
        low={c["strategy"]:{"tier":"LOW"} for c in candidates}
        high={c["strategy"]:{"tier":"HIGH"} for c in candidates}
        self.assertEqual(len(policy.select(candidates,low,slot=1)),8)
        self.assertEqual(len(policy.select(candidates,high,slot=1)),32)

    def test_priority_positions_cannot_block_uniform_lane(self):
        candidates=self.candidates()
        for row in candidates:row["priority_available"]=False
        selected=policy.select(candidates,{},slot=32)
        self.assertEqual(len(selected),8)
        self.assertTrue(all(row["lane"]=="EXPLORATION" for row in selected))

    def test_children_need_all_low_parents_and_start_with_zero_inherited_evidence(self):
        child=next(h for h in registry.catalog() if h.parents)
        tiers={h.id:{"needs_redevelopment":False} for h in registry.catalog()}
        for parent in child.parents[:-1]:tiers[parent]["needs_redevelopment"]=True
        self.assertFalse(engine.activate_children(tiers,{},"2026-03-12T00:00:00Z"))
        tiers[child.parents[-1]]["needs_redevelopment"]=True
        activated=engine.activate_children(tiers,{},"2026-03-12T00:00:00Z")
        self.assertEqual(activated[child.id]["parent_outcomes_inherited"],0)
        self.assertEqual(activated,engine.activate_children(tiers,activated,"2026-04-01T00:00:00Z"))


class ReplayTests(unittest.TestCase):
    def setUp(self):self.now=dt.datetime(2026,1,1,10,1,tzinfo=UTC)

    def events(self,delay_minutes=60,*,exit_size="10"):
        first=engine.seal(tick(self.now),[])
        second=engine.seal(tick(self.now+dt.timedelta(minutes=delay_minutes),
                               price=102,size=exit_size),[first])
        return [first,second]

    def test_actual_observation_closes_at_horizon_and_replay_is_repeatable(self):
        events=self.events()
        with patch.object(registry,"proposals",return_value={"A1:trend:H4":1}):
            a=engine.replay(events)
            self.assertEqual(a,engine.replay(events))
        self.assertEqual(a["closed_shadow_pairs"],2)
        self.assertEqual(a["tier_counts"],{"WARMUP":174})
        self.assertEqual(a["real_orders"],0)

    def test_no_early_exit_or_overlapping_pair(self):
        with patch.object(registry,"proposals",return_value={"A1:trend:H4":1}):
            result=engine.replay(self.events(delay_minutes=30))
        self.assertEqual(result["closed_shadow_pairs"],0)
        self.assertEqual(result["admissions_by_lane"]["EXPLORATION"],2)
        self.assertEqual(result["pending_shadow_pairs"],4)

    def test_late_or_unknown_funding_outcomes_cannot_change_tiers(self):
        pos={"id":"p","strategy":STRATEGY,"symbol":"BTC","lane":"EXPLORATION",
            "side":1,"control_side":-1,"entry_ms":int(self.now.timestamp()*1000),
            "due_ms":int(self.now.timestamp()*1000)+3600000,
            "entry_book":asset("BTC",self.now)["book"]}
        after=self.now+dt.timedelta(hours=2)
        result=engine.outcome(pos,asset("BTC",after),int(after.timestamp()*1000),[])
        self.assertFalse(result["eligible"])
        self.assertFalse(result["timely"])
        self.assertIsNone(result["stress_pct"])

    def test_exit_depth_uses_original_quantity_not_remaining_dollar_notional(self):
        after=self.now+dt.timedelta(hours=1)
        end=int(after.timestamp()*1000)
        pos={"id":"p","strategy":STRATEGY,"symbol":"BTC","lane":"EXPLORATION",
            "side":1,"control_side":-1,"entry_ms":int(self.now.timestamp()*1000),
            "due_ms":end,"entry_book":asset("BTC",self.now)["book"]}
        exit_asset=asset("BTC",after,price=200,size="1.5")
        result=engine.outcome(pos,exit_asset,end,exit_asset["funding"])
        self.assertFalse(result["exit_depth_sufficient"])

    def test_mutation_epoch_changes_and_missing_journal_files_fail(self):
        events=self.events()
        changed=copy.deepcopy(events)
        changed[0]["tick"]["assets"]["BTC"]["book"]["bid"]="500"
        with self.assertRaisesRegex(ValueError,"hash chain"):engine.replay(changed)
        changed=copy.deepcopy(events[:1])
        changed[0]["code_contract"]["registry"]="changed"
        changed[0]["hash"]=engine.sha({k:v for k,v in changed[0].items() if k!="hash"})
        with self.assertRaisesRegex(ValueError,"EPOCH_FROZEN"):engine.replay(changed)
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)/"observations";directory.mkdir()
            (directory/"00000002.json.gz").write_bytes(gzip.compress(engine.canonical(events[0]).encode()))
            with self.assertRaisesRegex(ValueError,"missing/unexpected"):engine.read_events(folder)

    def test_missing_or_changed_report_does_not_repair_silently(self):
        events=self.events()[:1]
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)/"observations";directory.mkdir()
            (directory/"00000001.json.gz").write_bytes(gzip.compress(engine.canonical(events[0]).encode()))
            with self.assertRaisesRegex(ValueError,"missing/divergent"):engine.verify_saved(folder)
            report=engine.replay(events);engine.write_report(folder,report)
            engine.verify_saved(folder)
            report["real_orders"]=1;engine.write_report(folder,report)
            with self.assertRaisesRegex(ValueError,"missing/divergent"):engine.verify_saved(folder)


class SourceHistoryTests(unittest.TestCase):
    def test_missing_expected_funding_and_changed_schedule_are_unknown(self):
        hour=3600000
        rates=[[EPOCH+i*8*hour,.0001] for i in range(4)]
        entry=EPOCH+25*hour
        contract=engine.funding_contract(rates,entry)
        self.assertIsNotNone(contract)
        self.assertTrue(engine.funding_complete(rates,contract,entry,entry+hour))
        self.assertFalse(engine.funding_complete(rates,contract,entry,EPOCH+33*hour))
        complete=rates+[[EPOCH+32*hour,.0001]]
        self.assertTrue(engine.funding_complete(complete,contract,entry,EPOCH+33*hour))
        changed=complete+[[EPOCH+30*hour,.0001]]
        self.assertFalse(engine.funding_complete(changed,contract,entry,EPOCH+33*hour))

    def test_source_rejects_unconfirmed_future_and_stale_inputs(self):
        now=dt.datetime(2026,1,1,10,1,tzinfo=UTC)
        row=asset("BTC",now)
        row["candles"][-1][0]+=900000
        with self.assertRaises(ValueError):source.validate_asset("BTC",row,now=now)
        row=asset("BTC",now)
        row["funding"].append([int(now.timestamp()*1000)+1,.001])
        with self.assertRaisesRegex(ValueError,"future funding"):source.validate_asset("BTC",row,now=now)

    def test_partial_failure_is_explicit_and_zero_sources_fail(self):
        now=dt.datetime(2026,1,1,10,1,tzinfo=UTC)
        def fetch(symbol,**kwargs):
            if symbol=="SOL":raise ValueError("source down")
            return asset(symbol,now)
        with patch.object(source,"fetch_asset",side_effect=fetch):
            capture=source.capture(symbols=("BTC","ETH","SOL"),clock=lambda:now)
            self.assertIn("SOL",capture["source_failures"])
            self.assertEqual(len(capture["assets"]),2)
        with patch.object(source,"fetch_asset",side_effect=ValueError("down")):
            with self.assertRaisesRegex(ValueError,"fewer than two"):source.capture(clock=lambda:now)

    def test_private_order_endpoints_are_unreachable(self):
        with self.assertRaisesRegex(ValueError,"PUBLIC_SOURCE_ONLY"):
            source.get("/trade/order","BTC")

    def test_historical_hash_mutation_rejected(self):
        now=dt.datetime(2026,1,1,10,1,tzinfo=UTC)
        body={"schema":"adaptive-historical-source-v1","instrument":"BTC-USDT-SWAP",
              "candles":asset("BTC",now)["candles"],"funding":[],"real_orders":0}
        item={**body,"hash":engine.sha(body)}
        history.validate(item,"BTC")
        item["candles"][-1][4]=100000
        with self.assertRaisesRegex(ValueError,"hash/source"):history.validate(item,"BTC")


if __name__=="__main__":unittest.main()
