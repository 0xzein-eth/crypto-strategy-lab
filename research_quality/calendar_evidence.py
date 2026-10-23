"""Conservative descriptive calendar-cluster intervals for exploratory research.

Do not treat overlapping asset trades as independent. Multiplicity correction
is conservative Bonferroni across registered hypotheses; this is NOT an
untouched forward test or a guarantee of future profitability.
"""
from collections import defaultdict
from statistics import mean, stdev, NormalDist
import math
import datetime as dt

def interval_by_entry_day(rows, *, families, minimum_days=20, minimum_rows=100):
    if isinstance(families,bool) or not isinstance(families,int) or not 1<=families<=10000:
        raise ValueError("invalid hypothesis count")
    if isinstance(minimum_days,bool) or not isinstance(minimum_days,int) or minimum_days<2:
        raise ValueError("invalid day threshold")
    if isinstance(minimum_rows,bool) or not isinstance(minimum_rows,int) or minimum_rows<1:
        raise ValueError("invalid row threshold")
    groups=defaultdict(list)
    n=0
    for day,value in rows:
        if not isinstance(day,str) or len(day)!=10:
            raise ValueError("invalid UTC date string")
        if dt.date.fromisoformat(day).isoformat()!=day:
            raise ValueError("invalid UTC calendar date")
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError("nonfinite strategy outcome")
        groups[day].append(float(value))
        n+=1
    d=len(groups)
    result={"hypothetical_rows":n,"distinct_entry_days":d,
            "effective_sample_unit":"UTC_ENTRY_DAY",
            "familywise_hypotheses":families,
            "bonferroni_descriptive_not_oos_proof":True,
            "lcb_pct":None,"ucb_pct":None,
            "mean_day_equal_weight_pct":None,
            "enough_for_descriptive_interval":n>=minimum_rows and d>=minimum_days}
    if not d:
        return result
    daily=[mean(v) for _,v in sorted(groups.items())]
    result["mean_day_equal_weight_pct"]=round(mean(daily),7)
    if not result["enough_for_descriptive_interval"]:
        return result
    # Approximate normal day-level interval; labels explicitly descriptive.
    critical=NormalDist().inv_cdf(1-0.05/(2*families))
    standard_error=stdev(daily)/math.sqrt(d)
    result["lcb_pct"]=round(mean(daily)-critical*standard_error,7)
    result["ucb_pct"]=round(mean(daily)+critical*standard_error,7)
    return result
