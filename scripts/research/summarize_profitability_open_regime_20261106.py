"""Read-only fixed open-regime two-arm summary."""
import json,hashlib
from pathlib import Path
from scripts.research.summarize_cross_month_held_peak_20261105 import metrics
from scripts.research.attribute_daily_regime_pre2026_20261106 import underwater
ROOT=Path(__file__).resolve().parents[2]
def main():
 out=[];pins={}
 for mode in ('SMA200','EMA20'):
  path=ROOT/f'tmp/profitability_open_regime_20261106_{mode}.json';pins[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest();doc=json.loads(path.read_text())
  for r in doc['results']:
   prefix=[x for x in r['ledger'] if x['date']<='2025-12-31'];m=metrics(prefix,r['warmup']['anchor'],0);m['fills']=None
   out.append(dict(mode=mode,window=r['window'],metrics=r['metrics'],cost=r['slippage_cost_proxy'],initial_plus_switches=len(r['transitions']),groups=r['groups'],through2025=m,underwater=underwater(r['ledger']),missing=r['missing'],qqq_price=r['qqq_price_5bp_reference']['metrics']))
 (ROOT/'tmp/profitability_open_regime_summary_20261106.json').write_text(json.dumps(dict(results=out,source_hashes=pins),indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
