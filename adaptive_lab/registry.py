"""Predeclared bounded catalog; existing v2/v9 experiments stay unchanged."""
from dataclasses import dataclass, asdict
import hashlib
import json

from research_v9.factory import Features, Variant, signal

VERSION="adaptive-crypto-shadow-registry-v1"
HORIZONS=(4,8,16,32,48,96)
SYMBOLS=("BTC","ETH","SOL","LINK","XRP","ADA","AVAX","DOGE",
         "DOT","NEAR","LTC","SUI","BNB","TRX","ATOM","APT")
# Explicit economic families and frozen parameters, not a fitted grid.
SPECS={
    "trend":(12,.003,60),"momentum":(16,.004,0),
    "mean_revert":(20,1.8,0),"breakout":(20,1.2,0),
    "rsi_revert":(14,30,0),"donchian":(40,1.1,0),
    "ztrend":(20,1.0,0),"rsi_trend":(14,60,0),
    "compression_breakout":(20,.65,0),"volatility_impulse":(20,1.25,0),
    "trend_reclaim":(20,.1,50),"volume_climax_fade":(20,2.0,0),
    "rsi_recovery":(14,30,0),"inside_bar_release":(20,1.15,50),
    "band_reentry":(20,1.8,0),"vwap_trend_reclaim":(20,1.0,50),
    "efficient_trend":(8,.75,50),"range_failure_revert":(20,1.0,0),
    "momentum_acceleration":(16,.2,50),"volume_followthrough":(20,1.2,50),
    "pullback_channel":(20,.1,50),
    "atr_breakout":(24,.15,0),"slope_reversion":(32,1.8,0),
    "timeframe_agreement":(96,.005,0),
}
RECIPES={
    "trend_breakout_mix":("trend","breakout","donchian"),
    "reversion_mix":("mean_revert","rsi_revert","band_reentry"),
    "momentum_mix":("momentum","momentum_acceleration","efficient_trend"),
    "pullback_mix":("trend_reclaim","vwap_trend_reclaim","pullback_channel"),
    "volume_mix":("volatility_impulse","volume_followthrough","inside_bar_release"),
}


@dataclass(frozen=True)
class Hypothesis:
    family: str
    horizon: int
    parents: tuple=()

    @property
    def id(self):
        return f"A1:{self.family}:H{self.horizon}"

    def record(self):
        return {**asdict(self),"id":self.id,
                "parameters":SPECS.get(self.family),"version":VERSION}


def catalog():
    return tuple(Hypothesis(family,h) for family in SPECS for h in HORIZONS)+tuple(
        Hypothesis(family,h,tuple(f"A1:{p}:H{h}" for p in parents))
        for family,parents in RECIPES.items() for h in HORIZONS)


def digest():
    payload={"catalog":[x.record() for x in catalog()],"symbols":SYMBOLS}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def base_signals(bars):
    features=Features(bars)
    return votes_at(features,len(bars)-1)


def votes_at(features,j):
    """Shared as-of features for bounded historical diagnostics."""
    if j<127:raise ValueError("128 genuinely completed bars required")
    votes={}
    for family,(n,gate,slow) in SPECS.items():
        if family=="atr_breakout":
            width=sum(features.high[k]-features.low[k] for k in range(j-n,j))/n
            votes[family]=(1 if features.close[j]>max(features.high[j-n:j])+gate*width
                           else -1 if features.close[j]<min(features.low[j-n:j])-gate*width else 0)
        elif family=="slope_reversion":
            sd=features.std(j,n)
            z=(features.close[j]-features.mean(j,n))/sd if sd else 0
            flat=abs(features.mean(j,20)/features.mean(j,50)-1)<.01
            votes[family]=(-1 if flat and z>gate else 1 if flat and z< -gate else 0)
        elif family=="timeframe_agreement":
            moves=[features.close[j]/features.close[j-k]-1 for k in (4,16,n)]
            votes[family]=(1 if min(moves)>gate else -1 if max(moves)< -gate else 0)
        else:
            votes[family]=signal(features,Variant(family,n,gate,slow,16),j)
    return votes


def proposals(bars,active_children=()):
    votes=base_signals(bars)
    output={}
    for hypothesis in catalog():
        if hypothesis.parents:
            if hypothesis.id not in active_children:
                continue
            values=[votes[parent] for parent in RECIPES[hypothesis.family]]
            nonzero={v for v in values if v}
            side=(next(iter(nonzero)) if len(nonzero)==1 and sum(v!=0 for v in values)>=2 else 0)
        else:
            side=votes[hypothesis.family]
        if side:output[hypothesis.id]=side
    return output
