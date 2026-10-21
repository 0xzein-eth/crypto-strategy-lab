"""Versioned, geographically separated Nasdaq-listed / IDX LQ45 cohorts.

Membership is AS-OF, not backfilled historically: researching former
constituents in preceding years otherwise introduces severe survivor bias.
NASDAQ group is a declared Nasdaq-listed research subset, NOT an assertion
that every member is an NDX constituent. LQ45 is the 2026-08-03..10-30
published 45-name snapshot; it expires fail-closed on October 31.
"""
import datetime as dt
from zoneinfo import ZoneInfo

NASDAQ=(
 "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO",
 "AMD","INTC","ADBE","CSCO","AMAT","QCOM","TXN","COST",
 "PEP","NFLX","PYPL","ASML","INTU","MU","MRNA","ISRG","GILD",
)
LQ45_CODES=(
 "AADI","ADMR","ADRO","AKRA","AMMN","AMRT","ANTM","ASII",
 "BBCA","BBNI","BBRI","BBTN","BMRI","BRPT","BUMI","CPIN",
 "CUAN","DEWA","EMTK","ESSA","EXCL","GOTO","HRTA","ICBP",
 "INCO","INDF","INDY","INKP","ISAT","ITMG","JPFA","KLBF",
 "MAPI","MBMA","MDKA","MEDC","NCKL","PGAS","PGEO","PTBA",
 "SCMA","TLKM","UNTR","UNVR","WIFI",
)
LQ45=tuple(code+".JK" for code in LQ45_CODES)
LQ45_START=dt.date(2026,8,3)
LQ45_END=dt.date(2026,10,30)

MARKETS={
 "NASDAQ":{
   "symbols":NASDAQ,
   "venue":"NASDAQ","currency":"USD","timezone":"America/New_York",
   "benchmark":"^NDX","min_complete_local_hour":19,
   "initial_paper_cash":"10000.00","lot":1,
   "buy_fee_pct":0.10,"sell_fee_pct":0.10,
   "adverse_impact_each_side_pct":0.10,"settlement_sessions":1,
   "membership_source":"Nasdaq-listed research shortlist, not entire Nasdaq-100",
   "membership_effective":"2026-10-21",
   "membership_expiry":None,
 },
 "LQ45":{
   "symbols":LQ45,
   "venue":"IDX","currency":"IDR","timezone":"Asia/Jakarta",
   "benchmark":"^JKSE","min_complete_local_hour":18,
   "initial_paper_cash":"10000000.00","lot":100,
   "buy_fee_pct":0.15,"sell_fee_pct":0.25,
   "adverse_impact_each_side_pct":0.10,"settlement_sessions":2,
   "membership_source":"https://www.investasiku.id/eduvest/saham/perusahaan-di-bei-yang-masuk-lq45",
   "membership_official_reference":"https://www.idx.co.id/id/data-pasar/data-saham/indeks-saham/",
   "membership_effective":LQ45_START.isoformat(),
   "membership_expiry":LQ45_END.isoformat(),
 }
}


def market(name, *, now=None):
    if name not in MARKETS:
        raise ValueError("MARKET_INVALID: only NASDAQ and LQ45 are available")
    config=MARKETS[name]
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("CLOCK_INVALID: require timezone-aware timestamp")
    d=now.astimezone(ZoneInfo(config["timezone"])).date()
    if config["membership_expiry"] and d > dt.date.fromisoformat(config["membership_expiry"]):
        raise ValueError("MEMBERSHIP_EXPIRED: update frozen LQ45 list for next IDX review; no stale trades")
    return config


def verify():
    if len(set(NASDAQ))!=len(NASDAQ) or len(set(LQ45))!=45:
        raise ValueError("UNIVERSE_INVALID: duplicate or incomplete cohort")
    if len(set(LQ45_CODES))!=45 or ("SMGR.JK" in LQ45 or "TOWR.JK" in LQ45):
        raise ValueError("MEMBERSHIP_INVALID: removed LQ45 members")
    if "INDY.JK" not in LQ45 or "NCKL.JK" not in LQ45:
        raise ValueError("MEMBERSHIP_INVALID: missing new LQ45 members")
    if any(not s.endswith(".JK") for s in LQ45):
        raise ValueError("UNIVERSE_INVALID: wrong IDX suffix")
    if any(not s.isalpha() or not s.isupper() for s in NASDAQ):
        raise ValueError("UNIVERSE_INVALID: invalid Nasdaq listing ticker")
    if MARKETS["NASDAQ"]["currency"]==MARKETS["LQ45"]["currency"]:
        raise ValueError("MONEY_INTEGRITY: US and Indonesia must remain separate")
    return True
verify()
