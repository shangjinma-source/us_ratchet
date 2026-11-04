"""Manifest-directed read-only raw-date inventory, no membership certification."""
import json,gzip,csv,io
from pathlib import Path
from datetime import datetime,date,timedelta
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2]
def run():
 d=json.loads((ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json').read_bytes());a=d['assembled'];plan=a['monthly_inputs'][-1]['search_arguments'];rows=[];cache={}
 execution={str(date(2026,8,1)+timedelta(days=i)) for i in range(31) if (date(2026,8,1)+timedelta(days=i)).weekday()<5}
 for sid in plan['prices']:
  ticker=a['metadata'][sid]['ticker'];dates=set();paths=[];errors=[]
  for seg in a['source_provenance'].get(sid,{}).get('segments',[]):
   name=seg['source_path']
   if name in paths:continue
   paths.append(name)
   try:
    if name not in cache:
     raw=(ROOT/name).read_bytes();raw=gzip.decompress(raw) if raw[:2]==b"\x1f\x8b" else raw
     if name.endswith('.csv'):
      cache[name]={r['Date'] for r in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))) if all(r.get(k) for k in ['Open','High','Low','Close'])}
      dates|=cache[name];continue
     body=json.loads(raw)
     if 'rows' in body:
      cache[name]={r['date'] for r in body['rows'] if all(r.get(k) for k in ['open','high','low','close'])}
      dates|=cache[name];continue
     r=body['chart']['result'][0];q=r['indicators']['quote'][0]
     cache[name]={datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat() for i,t in enumerate(r['timestamp']) if all(q.get(k,[None]*len(r['timestamp']))[i] is not None for k in ['open','high','low','close'])}
    dates|=cache[name]
   except Exception as e:errors.append(type(e).__name__)
  train=sorted(x for x in dates if x<='2026-07-31');missing=sorted(execution-dates)
  rows.append(dict(ticker=ticker,security_id=sid,source_paths=paths,raw_training_bars=len(train),has_253_raw_bars=len(train)>=253,has_decision_bar='2026-07-31' in dates,august_missing_dates=missing,errors=errors))
 result=dict(scope='6/30 admitted price domain only; not 7/31 domain. Raw date coverage not nominal unit/action certification. August weekdays provisional calendar.',count=len(rows),source_files_read=len(cache),has_253=sum(r['has_253_raw_bars'] for r in rows),has_july31=sum(r['has_decision_bar'] for r in rows),august_full=sum(not r['august_missing_dates'] for r in rows),rows=rows)
 out=ROOT/'tmp/post_july_inventory_20261104/local_gap.json';out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k!='rows'}));print('gaps',[(r['ticker'],r['raw_training_bars'],len(r['august_missing_dates']),r['errors']) for r in rows if not r['has_253_raw_bars'] or not r['has_decision_bar'] or r['august_missing_dates']])
if __name__=='__main__':run()
