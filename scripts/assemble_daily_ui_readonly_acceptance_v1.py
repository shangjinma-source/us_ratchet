"""Assemble read-only Cua DOM + authentic server journal evidence for V6.
No browser or preview invocation. Only prepare/finish use read-only account GETs.
"""
import argparse,json,re,sqlite3
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import requests
from review_daily_ui_capture_v6 import review,require

def now():return datetime.now(timezone.utc).isoformat()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def read(path):return json.loads(path.read_bytes())
def connection(root):return sqlite3.connect((root/'data/strategy_account/daily_advice_v1.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)
def get_json(url):
 started=now();response=requests.get(url,timeout=15);response.raise_for_status()
 return response.json(),dict(url=url,method='GET',started_at=started,received_at=now(),status=response.status_code,response_sha256=sha256(response.content).hexdigest())
def prepare(root,out,log):
 out.mkdir(parents=True,exist_ok=False)
 account,account_receipt=get_json('http://127.0.0.1:8010/api/strategy-account')
 target,target_receipt=get_json('http://127.0.0.1:8010/api/strategy-account/target')
 save(out/'account_before.json',account);save(out/'target_before.json',target)
 with connection(root) as db:sequence=db.execute('select coalesce(max(sequence),0) from advice_events').fetchone()[0]
 checkpoint=dict(schema='READONLY_DOM_ACCEPTANCE_CHECKPOINT_V1',prepared_at=now(),journal_sequence=sequence,log_path=str(log.resolve()),log_start_byte=log.stat().st_size,account_receipt=account_receipt,target_receipt=target_receipt)
 save(out/'checkpoint.json',checkpoint)
 return dict(status='PREPARED_WAITING_FOR_ONE_CUA_RELOAD_AND_DOM',output=str(out))
def finish(root,out,dom_path):
 checkpoint=read(out/'checkpoint.json');dom=read(dom_path)
 require(dom.get('capture_schema')=='DAILY_FOUR_COLUMN_DOM_CAPTURE_V2','REAL_DOM_REQUIRED')
 require(datetime.fromisoformat(dom['observed_at'].replace('Z','+00:00'))>=datetime.fromisoformat(checkpoint['prepared_at']),'DOM_BEFORE_CHECKPOINT')
 after,after_receipt=get_json('http://127.0.0.1:8010/api/strategy-account');save(out/'account_after.json',after)
 with connection(root) as db:
  rows=db.execute('select body,digest from advice_events where sequence>? order by sequence',(checkpoint['journal_sequence'],)).fetchall()
 require(len(rows)==1,'EXACTLY_ONE_NEW_JOURNAL_EVENT_REQUIRED')
 raw,digest=rows[0];raw=raw.encode() if isinstance(raw,str) else raw
 require(sha256(raw).hexdigest()==digest,'JOURNAL_DIGEST_MISMATCH');event=json.loads(raw)
 require(datetime.fromisoformat(event['started_at'])>=datetime.fromisoformat(checkpoint['prepared_at']),'EVENT_BEFORE_CAPTURE')
 (out/'journal_event.json').write_bytes(raw)
 log=Path(checkpoint['log_path']);end=log.stat().st_size
 with log.open('rb') as stream:stream.seek(checkpoint['log_start_byte']);audit_raw=stream.read(end-checkpoint['log_start_byte'])
 (out/'server_log_segment.txt').write_bytes(audit_raw)
 writes=re.findall(rb'"(POST|PUT|PATCH|DELETE) ([^ ]+) HTTP/[^\"]+" (\d{3})',audit_raw)
 entries=[dict(method=m.decode(),path=p.decode(),status=int(s)) for m,p,s in writes]
 allowed=[row for row in entries if row['method']=='POST' and row['path']=='/api/strategy-daily-v3/preview' and row['status']==200]
 unexpected=[row for row in entries if row not in allowed]
 require(len(allowed)==1 and not unexpected,'SERVER_LOG_WRITE_AUDIT_FAILED')
 before=read(out/'account_before.json');target_response=read(out/'target_before.json')
 account_before=before['account'];account_after=after['account'];target=target_response if 'target_id' in target_response else target_response.get('target')
 require(isinstance(target,dict),'TARGET_RESPONSE_SHAPE_UNSUPPORTED')
 assembled=dict(dom,api_state=dict(account=account_after,target=target,daily=event['response']),account_before=account_before,account_after=account_after,cash_posts_intercepted=0,unexpected_writes=[],write_audit=dict(source='Actual uvicorn access log bounded byte interval; no browser interception',entries=entries,start_byte=checkpoint['log_start_byte'],end_byte=end,sha256=sha256(audit_raw).hexdigest()),external_daily_source=dict(kind='SERVER_JOURNAL_SAVED_RESPONSE_NOT_BROWSER_HIDDEN_STATE_OR_CAPTURED_HTTP',event_id=event['event_id'],sha256=digest),account_after_receipt=after_receipt)
 save(out/'assembled_capture.json',assembled)
 result=review(assembled);result['external_daily_source']=assembled['external_daily_source'];result['write_audit_scope']='Observed server access log interval only; no interception or cash-button execution certification'
 save(out/'review.json',result);return result
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','finish']);parser.add_argument('--root',default='.');parser.add_argument('--out',required=True);parser.add_argument('--log');parser.add_argument('--dom');args=parser.parse_args()
 result=prepare(Path(args.root).resolve(),Path(args.out),Path(args.log)) if args.mode=='prepare' else finish(Path(args.root).resolve(),Path(args.out),Path(args.dom))
 print(json.dumps(result,ensure_ascii=False))
