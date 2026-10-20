"""Synthetic fixtures verify IDX future-only paper/account constraints.

No synthetic source data ever enter operational journal. These tests create
EXPLICIT fake IDX bar series in memory to detect timing, cash, lot, T+2,
provider mismatch, corporate action and hash tampering regressions.
"""
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from stock_lab import source, strategies, engine as e

UTC=dt.timezone.utc
WIB=source.WIB


def session_dates(n=110):
    day=dt.date(2026,2,2)
    dates=[]
    while len(dates)<n:
        if day.weekday()<5:
            dates.append(day)
        day+=dt.timedelta(days=1)
    return dates


DATES=session_dates()
BARS=[]
for i,day in enumerate(DATES):
    price=1000.0 if i<90 else 1000.0+i-90
    if i==90:price=1040.0
    if i==91:price=1045.0
    if i==92:price=970.0
    if i>=93:price=955.0
    BARS.append({
        "date":day.isoformat(),"open":1000 if i<90 else
        (1037 if i==90 else 1042 if i==91 else 962 if i==92 else 952),
        "high":max(price,1000 if i<90 else 0)+6,
        "low":min(price,1000 if i<90 else price)-6,
        "close":price,
        "volume":2_000_000 if i>=90 else 800_000,
    })

# Synthetic fixtures must themselves satisfy realistic daily OHLC order.
for row in BARS:
    row["high"]=max(row["open"],row["close"])+6
    row["low"]=min(row["open"],row["close"])-6


def make_feed(index, *, actions=None, series=None):
    rows=(series or BARS)[:index+1]
    day=dt.date.fromisoformat(rows[-1]["date"])
    seen=dt.datetime.combine(day,dt.time(18,30),tzinfo=WIB)
    markets={}
    for symbol in source.SYMBOLS:
        markets[symbol]={
            "provider":source.PROVIDER,"venue":"IDX","currency":"IDR",
            "instrument":symbol,"observed_at":source.iso(seen),
            "last_complete_session_date":day.isoformat(),
            "history":rows,"history_sha256":source.sha(rows),
            "actions":actions or {},
        }
    return {"source_policy":"idx-yahoo-eod-unofficial-2026-10-20-v1",
            "date":day.isoformat(),"captured_at_utc":source.iso(seen),
            "markets":markets,"market_session_calendar_verified":False,
            "no_intraday_book_or_actual_broker_fills":True,
            "never_ordered_stocks":True}


def yahoo_fixture(now,*,wrong_currency=False,incomplete=False):
    stamps=[int(dt.datetime.combine(dt.date.fromisoformat(r["date"]),
              dt.time(9,0),tzinfo=WIB).timestamp()) for r in BARS[:94]]
    q={key:[r[key] for r in BARS[:94]]
       for key in ("open","high","low","close","volume")}
    if incomplete:q["close"][-1]=None
    return {"chart":{"error":None,"result":[{
        "meta":{"symbol":"BBCA.JK","currency":"USD" if wrong_currency else "IDR",
                "exchangeTimezoneName":"Asia/Jakarta",
                "instrumentType":"EQUITY"},
        "timestamp":stamps,"indicators":{"quote":[q]},
        "events":{"dividends":{},"splits":{}},
    }]}}


class MarketSourceTests(unittest.TestCase):
    def test_official_market_schedule_not_faked(self):
        self.assertEqual(len(source.SYMBOLS),6)
        self.assertTrue(all(x.endswith(".JK") for x in source.SYMBOLS))
        self.assertIn("query1.finance.yahoo.com",source.endpoint("BBCA.JK"))
        with self.assertRaisesRegex(ValueError,"ticker"):
            source.endpoint("BTC-USD")
        with self.assertRaisesRegex(ValueError,"endpoint"):
            source.get_json("https://www.okx.com/api/v5/trade/order")

    def test_only_completed_local_idx_daily_bar_and_correct_idr(self):
        test_day=DATES[93]
        at=dt.datetime.combine(test_day,dt.time(17,0),tzinfo=WIB)
        data=source.parse_chart(yahoo_fixture(at),"BBCA.JK",now=at)
        self.assertEqual(data["last_complete_session_date"],DATES[92].isoformat())
        later=dt.datetime.combine(test_day,dt.time(18,45),tzinfo=WIB)
        final=source.parse_chart(yahoo_fixture(later),"BBCA.JK",now=later)
        self.assertEqual(final["last_complete_session_date"],test_day.isoformat())
        self.assertEqual(final["currency"],"IDR")
        self.assertTrue(final["provider_is_not_official_idx"])
        self.assertFalse(final["book_bid_ask_verified"])
        with self.assertRaisesRegex(ValueError,"wrong IDX"):
            source.parse_chart(yahoo_fixture(later,wrong_currency=True),"BBCA.JK",now=later)
        with self.assertRaisesRegex(ValueError,"missing historical"):
            problematic=yahoo_fixture(later)
            problematic["chart"]["result"][0]["indicators"]["quote"][0]["open"][20]=None
            source.parse_chart(problematic,"BBCA.JK",now=later)

    def test_actual_late_session_null_is_not_a_zero_price(self):
        at=dt.datetime.combine(DATES[93],dt.time(18,30),tzinfo=WIB)
        parsed=source.parse_chart(yahoo_fixture(at,incomplete=True),"BBCA.JK",now=at)
        self.assertEqual(parsed["last_complete_session_date"],DATES[92].isoformat())


class CashPortfolioTests(unittest.TestCase):
    def test_no_preclose_source_or_lookahead(self):
        first=make_feed(90)
        shot=e.freeze_snapshot(first)
        self.assertEqual(set(shot["assets"]),set(source.SYMBOLS))
        self.assertEqual(shot["session"],DATES[90].isoformat())
        self.assertTrue(e.validate_snapshot(shot))
        altered=copy.deepcopy(shot)
        altered["assets"]["BBCA.JK"]["declared_decisions_for_NEXT_session"]["BREAKOUT20"]="EXIT"
        with self.assertRaisesRegex(ValueError,"SIGNAL_INTEGRITY"):
            e.validate_snapshot(altered)
        early=copy.deepcopy(shot)
        early["observed_at_utc"]=source.iso(dt.datetime.combine(
            DATES[90],dt.time(15,20),tzinfo=WIB))
        with self.assertRaisesRegex(ValueError,"before its market close"):
            e.validate_snapshot(early)

    def test_first_sample_is_only_observation_not_backfilled_trades(self):
        first=e.observe(make_feed(90),[])
        event,w,curve,shadow=first
        self.assertEqual(w["observation_sessions"],1)
        self.assertEqual(w["positions_opened"],0)
        self.assertEqual(w["positions_closed"],0)
        self.assertEqual(w["latest_simulated_equity_idr"],"10000000.00")
        self.assertEqual(w["real_broker_orders"],0)
        self.assertEqual(shadow["unresolved_future_horizon"],0)
        self.assertEqual(shadow["closed_rows"],[])
        self.assertEqual(len(curve),1)

    def test_next_session_hypothetical_open_cannot_buy_fractional_shares(self):
        first=e.observe(make_feed(90),[])
        second=e.observe(make_feed(91),[first[0]])
        self.assertIsNotNone(second)
        _,wallet,curve,sh=second
        self.assertGreater(wallet["positions_opened"],0)
        self.assertLessEqual(wallet["positions_opened"],3)
        self.assertTrue(all(p["shares"]%100==0 and p["shares"]>0
                            for p in wallet["open_positions_detail"]))
        self.assertLess(float(wallet["latest_settled_cash_idr"]),10_000_000)
        self.assertEqual(wallet["real_broker_orders"],0)
        self.assertTrue(wallet["one_day_later_OPEN_is_observed_only_after_the_daily_bar"])
        self.assertTrue(wallet["financial_edge_after_all_costs_unproven"])
        self.assertGreater(sh["unresolved_future_horizon"],0)
        self.assertEqual(wallet["positions_closed"],0)
        self.assertTrue(all(x["session"]<=DATES[91].isoformat() for x in curve))
        self.assertIsNone(wallet["win_rate_closed"])

    def test_open_position_size_ignores_unseen_same_day_close_and_volume(self):
        prior=e.observe(make_feed(90),[])
        reference=e.observe(make_feed(91),[prior[0]])
        altered=copy.deepcopy(BARS)
        altered[91]["close"]=1200.0
        altered[91]["volume"]=1
        altered[91]["high"]=max(altered[91]["open"],altered[91]["close"])+6
        altered[91]["low"]=min(altered[91]["open"],altered[91]["close"])-6
        changed=e.observe(make_feed(91,series=altered),[prior[0]])
        self.assertEqual(reference[1]["positions_opened"],
                         changed[1]["positions_opened"])
        self.assertEqual(reference[1]["open_positions_detail"],
                         changed[1]["open_positions_detail"])
        self.assertNotEqual(reference[1]["latest_simulated_equity_idr"],
                            changed[1]["latest_simulated_equity_idr"])
        # A genuine OPEN observed after the fact remains a hypothetical
        # fill model. Closing price and future volume are NOT sizing inputs.

    def test_hash_chain_tampering_and_duplicate_session_fail(self):
        one=e.observe(make_feed(90),[])
        two=e.observe(make_feed(91),[one[0]])
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"journal.jsonl"
            p.write_text("".join(source.canonical(x)+"\n" for x in
                                (one[0],two[0])),encoding="utf-8")
            self.assertEqual(len(e.read_events(p)),2)
            corrupted=copy.deepcopy(two[0])
            corrupted["snapshot"]["assets"]["BBCA.JK"]["bars"][-1]["close"]=999999
            p.write_text(source.canonical(one[0])+"\n"+source.canonical(corrupted)+"\n")
            with self.assertRaisesRegex(ValueError,"INTEGRITY_FAILURE"):
                e.read_events(p)
        self.assertIsNone(e.observe(make_feed(90),[one[0]]))
        self.assertIsNone(e.observe(make_feed(91),[one[0],two[0]]))

    def test_split_while_holding_halts_without_fabricated_share_conversion(self):
        one=e.observe(make_feed(90),[])
        two=e.observe(make_feed(91),[one[0]])
        split={DATES[92].isoformat():{"split":{"numerator":2,"denominator":1}}}
        with self.assertRaisesRegex(ValueError,"CORPORATE_ACTION_UNMODELED"):
            e.observe(make_feed(92,actions=split),[one[0],two[0]])

    def test_no_pending_sale_proceeds_rereinvested_before_conservative_settlement(self):
        events=[]
        for index in range(90,98):
            outcome=e.observe(make_feed(index),events)
            self.assertIsNotNone(outcome)
            events.append(outcome[0])
        w,curve,shadow=e.replay(events)
        self.assertEqual(w["real_broker_orders"],0)
        self.assertTrue(w["capital_unavailable_until_T2_plus_safety_session"])
        self.assertGreaterEqual(w["positions_closed"],0)
        self.assertEqual(w, e.replay(events)[0])
        self.assertEqual(len(curve),len(events))
        self.assertEqual(shadow["source_hash"],events[-1]["hash"])
        for day in curve:
            self.assertGreaterEqual(float(day["settled_cash_idr"]),0)
            self.assertGreaterEqual(float(day["unsettled_sale_cash_idr"]),0)

    def test_amount_to_buy_never_exceeds_cash_and_round_lots(self):
        shares=e._units_to_buy(e.dec(1_000_000),e.dec(50_000),2_000_000,e.dec(10_000_000))
        self.assertEqual(shares,0)
        shares=e._units_to_buy(e.dec(10_000_000),e.dec(1000),2_000_000,e.dec(10_000_000))
        self.assertEqual(shares%100,0)
        self.assertLessEqual(shares*1000,3_000_000)
        self.assertEqual(e._units_to_buy(e.dec(10_000_000),e.dec(1000),1,e.dec(10_000_000)),0)

    def test_candidate_strategy_inputs_are_trailing_only(self):
        f1=strategies.signals(BARS[:91])
        f2=strategies.signals(BARS[:91])
        self.assertEqual(f1,f2)
        self.assertEqual(set(f1),set(strategies.ARMS))
        self.assertTrue(all(x in ("BUY","EXIT","FLAT") for x in f1.values()))
        modified=copy.deepcopy(BARS)
        modified[93]["close"]=10_000
        self.assertEqual(strategies.signals(modified[:91]),f1)


if __name__=="__main__":
    unittest.main()
