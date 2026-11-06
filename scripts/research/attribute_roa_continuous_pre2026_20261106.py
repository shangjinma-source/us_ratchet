"""Read-only pre-2026 and underwater attribution; no strategy rerun."""
import json,hashlib
from pathlib import Path
from scripts.research.summarize_cross_month_held_peak_20261105 import metrics
from scripts.research.screen_profitability_daily_regime_20261106 import read_qqq
ROOT=Path(__file__).resolve().parents[2]
def underwater(rows):
 peak=20000.;streak=longest=0
 for r in rows:
  if r['equity']>=peak:peak=r['equity'];streak=0
  else:streak+=1;longest=max(longest,streak)
 return dict(longest_underwater_sessions=longest,end_underwater_sessions=streak,end_underwater_pct=(1-rows[-1]['equity']/peak)*100)
def main():
 path=ROOT/'tmp/profitability_roa_continuous_20261106_SMA200.json';pins={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()};p=json.loads(path.read_text());qqq=read_qqq(pins);out=[]
 for r in p['results']:
  anchor=r['warmup']['anchor'];units=20000/(qqq[anchor]*1.0005)
  for label,rows in [('CANDIDATE',r['ledger']),('QQQ_PRICE_5BP',[dict(date=x['date'],equity=units*qqq[x['date']]) for x in r['ledger']])]:
   prefix=[x for x in rows if x['date']<='2025-12-31'];m=metrics(prefix,anchor,0);m['fills']=None
   out.append(dict(window=r['window'],label=label,full_underwater=underwater(rows),through2025=dict(end_date=prefix[-1]['date'],metrics=m,underwater=underwater(prefix))))
 (ROOT/'tmp/profitability_roa_continuous_pre2026_20261106.json').write_text(json.dumps(dict(status='READ_ONLY_DIAGNOSTIC_PATH_ATTRIBUTION',results=out,source_hashes=pins),indent=2))
if __name__=='__main__':main()
