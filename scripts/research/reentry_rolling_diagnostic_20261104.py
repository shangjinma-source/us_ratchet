"""Fixed existing-ledger diagnostic; no new strategy replay or selection."""
import json
from pathlib import Path
from fractions import Fraction
from hashlib import sha256
from datetime import date, timedelta
ROOT=Path(__file__).resolve().parents[2]
def metrics(values):
    peak=values[0]; drawdown=Fraction(0)
    for value in values:
        peak=max(peak,value); drawdown=max(drawdown,1-value/peak)
    return {"return":values[-1]/values[0]-1,"drawdown":drawdown}
def run():
    receipt=json.loads((ROOT/'research_contracts/reentry_repair_20261029/completion_receipt.json').read_bytes())
    comparison=json.loads((ROOT/'research_contracts/reentry_repair_20261029/comparison.json').read_bytes())
    for pins in (receipt['source_hashes'],comparison['source_hashes']):
        for name,expected in pins.items():
            assert sha256((ROOT/name).read_bytes()).hexdigest()==expected, name
    result={"scope":"Existing complete ledgers; overlapping 365-calendar-day windows, not independent OOS or new candidate backtest","windows":{},"sources":{}}
    for window,start in [("2021_2023","2020-12-31"),("2024_2026","2023-12-29")]:
        curves={}
        for mode in ["baseline","candidate"]:
            path=ROOT/f"tmp/reentry_repair_20261029/{mode}_{window}/book.json"
            raw=path.read_bytes();result["sources"][path.relative_to(ROOT).as_posix()]=sha256(raw).hexdigest();book=json.loads(raw)
            assert book["status"]=="COMPLETE"
            assert all(Fraction(r.get("external_flow","0"))==0 for r in book["daily_ledger"])
            curves[mode]=[(date.fromisoformat(start),Fraction(20000))]+[(date.fromisoformat(r["date"]),Fraction(r["equity"])) for r in book["daily_ledger"]]
        assert [d for d,v in curves["baseline"]]==[d for d,v in curves["candidate"]]
        dates=[d for d,v in curves["baseline"]]; annual={}; rolling=[]
        for year in sorted(set(d.year for d in dates[1:])):
            indices=[i for i,d in enumerate(dates) if d.year==year and i>0]; lo=indices[0]-1; hi=indices[-1]
            annual[str(year)]={mode:metrics([v for d,v in curve[lo:hi+1]]) for mode,curve in curves.items()}
        for end,day in enumerate(dates):
            cutoff=day-timedelta(days=365)
            if cutoff<dates[0]:continue
            begin=max(i for i,d in enumerate(dates[:end]) if d<=cutoff)
            pair={mode:metrics([v for d,v in curve[begin:end+1]]) for mode,curve in curves.items()}
            rolling.append(dict(start=str(dates[begin]),end=str(day),**pair))
        result["windows"][window]={"annual":annual,"rolling_count":len(rolling),"both_better":sum(r["candidate"]["return"]>=r["baseline"]["return"] and r["candidate"]["drawdown"]<=r["baseline"]["drawdown"] for r in rolling),"return_worse":sum(r["candidate"]["return"]<r["baseline"]["return"] for r in rolling),"drawdown_worse":sum(r["candidate"]["drawdown"]>r["baseline"]["drawdown"] for r in rolling),"rolling":rolling}
    out=ROOT/"tmp/reentry_rolling_diagnostic_20261104";out.mkdir(exist_ok=True);(out/"result.json").write_text(json.dumps(result,indent=2,default=float),encoding="utf-8")
    print(json.dumps({w:{k:v for k,v in r.items() if k!="rolling"} for w,r in result["windows"].items()},indent=2,default=float))
if __name__=="__main__":run()
