"""Read-only exact-key reuse candidates; never changes action admission."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[2];TMP=ROOT/'tmp'
def walk(v,pointer=''):
 if isinstance(v,dict):
  yield pointer,v
  for k,x in v.items():yield from walk(x,pointer+'/'+str(k))
 elif isinstance(v,list):
  for i,x in enumerate(v):yield from walk(x,pointer+'/'+str(i))
def main():
 gate=json.loads((TMP/'residual_momentum_action_coverage_20261106.json').read_text());events={}
 for r in gate:
  for e in r['gate'].get('unmapped_events',[]):events.setdefault((e['security_id'],e['date'],e['kind']),e)
 files=[]
 for folder in TMP.iterdir():
  if folder.is_dir() and folder.name.startswith(('rsi2_','momentum_','breakout','equal_four_','pullback_action','downside_')):
   for p in folder.rglob('*.json'):
    if p.stat().st_size<2000000 and any(t in p.name.lower() for t in ('review','mapping','supplement','batch','events')) and not any(t in p.name for t in ('failure_gate','execution_inputs','source_hash')):files.append(p)
 matches={k:[] for k in events};scanned=[]
 for p in files:
  raw=p.read_bytes()
  try:x=json.loads(raw)
  except (ValueError,UnicodeError):continue
  scanned.append(dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(raw).hexdigest()))
  for pointer,v in walk(x):
   sid=v.get('security_id');d=v.get('ex_date',v.get('date'));kind='dividends' if v.get('payment_date') and any(k in v for k in ('amount_per_share','amount','gross_amount_per_share','nominal_amount')) else 'splits' if v.get('type') in ('split','split_identity') and 'new_shares' in v else None
   key=(sid,d,kind)
   if key not in events:continue
   sources=v.get('source_sha256',{});checks=[]
   if isinstance(sources,dict):
    for source,digest in sources.items():
     q=ROOT/source;checks.append(dict(source=source,exists=q.exists(),hash_matches=q.exists() and hashlib.sha256(q.read_bytes()).hexdigest()==digest))
   matches[key].append(dict(path=str(p.relative_to(ROOT)),json_pointer=pointer,record=v,local_source_checks=checks,classification='EXACT_SID_DATE_TYPE_REVIEW_CANDIDATE_NOT_AUTO_ADMITTED'))
 rows=[dict(event=events[k],matches=matches[k],status='EXACT_KEY_REUSE_CANDIDATE' if matches[k] else 'NO_EXACT_REVIEW_IN_BOUNDED_SCAN') for k in sorted(events)]
 out=dict(status='READ_ONLY_NO_ADMISSION_CHANGE',unique_events=len(events),matched_events=sum(bool(r['matches']) for r in rows),unmatched_events=sum(not r['matches'] for r in rows),rows=rows,files=scanned,limits=['Exact SID/date/type does not certify amount currency coordinate or scope','No ticker-only alias matching; source hash missing is not proof','Only bounded review/mapping/supplement/event artifacts below listed research dirs; not exhaustive filesystem claim'])
 (TMP/'residual_momentum_review_reuse_20261106.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k not in ('rows','files')},indent=2));print('SCANNED',len(scanned));print('UNMATCHED',[(r['event']['ticker'],r['event']['date'],r['event']['kind']) for r in rows if not r['matches']])
if __name__=='__main__':main()
