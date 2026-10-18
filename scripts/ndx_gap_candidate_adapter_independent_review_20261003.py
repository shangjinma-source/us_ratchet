"""Independent saved adapter projection, no producer imports or parent audit calls."""
from pathlib import Path
from datetime import datetime
import csv
import io
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/cache/research/gap_candidate_calendar_adapter_20261003_v1'
RESULT='26937eec56063e30897823c759bc07c2d4b0b45d1e82f0161cf1c5261b11aa2f'
PUB='b2ef3c155f5378ae4ae8262b4e87d132d31fd64afc284ee1c4f82f987d069750'
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def equal(a,b):assert canonical(a)==canonical(b)
def read(path,h):
 b=Path(path).read_bytes();assert sha(b)==h;return json.loads(b)

def run():
 d=read(OUT/'evidence.json',RESULT);pub=read(OUT/'publication.json',PUB)
 assert {p.name for p in OUT.iterdir()}=={'started.json','evidence.json','publication.json'}
 assert d['schema']=='SOURCE_BOUND_GAP_CANDIDATE_CALENDAR_EVIDENCE_V1'
 assert pub['status']=='PUBLISHED_BLOCKED_EVIDENCE_ONLY_NO_OBSERVATION'
 equal(pub['evidence_reference'],dict(path=str(OUT/'evidence.json'),sha256=RESULT))
 sources=d['source_hashes'];refs=d['input_references'];assert len(sources)==18 and len(refs)==11
 equal(pub['source_hashes'],sources)
 for path,h in sources.items():assert sha(Path(path).read_bytes())==h
 parents={}
 for role,r in refs.items():
  assert sources[r['path']]==r['sha256']
  if role not in ('contract','user_choice','parent_sessions'):parents[role]=read(r['path'],r['sha256'])
 for role,field in [('policy','policy_reference'),('frontier','frontier_reference'),('capture','capture_reference')]:
  equal(parents[role+'_publication'][field],refs[role])
  equal(parents[role+'_publication']['source_hashes'],parents[role]['source_hashes'])
 equal(parents['ledger_publication']['artifacts']['ledger'],refs['ledger'])
 frontier=parents['frontier'];policy=parents['policy'];capture=parents['capture'];e=d['evidence']
 assert frontier['last_observed_session']=='2026-09-24' and frontier['last_accounted_session']=='2026-10-01'
 original=frontier['known_accounted_rows'];assert len(original)==65
 typed=[];projection=[];months={}
 for i,row in enumerate(original):
  gap=i>=60;assert row['kind']==('MISSED_OBSERVATION' if gap else 'SEALED_PARENT_OBSERVED_SESSION')
  t=dict(sequence=i+1,session=row['session'],kind=row['kind'],evidence_reference=dict(refs['frontier'],json_pointer=f'/known_accounted_rows/{i}'),seal_status='NOT_ATTEMPTED' if gap else 'UNKNOWN');typed.append(t)
  month=months.setdefault(row['session'][:7],dict(month=row['session'][:7],first_observed_session=None,observed_count=0,missed_count=0))
  first=not gap and month['first_observed_session'] is None
  if gap:month['missed_count']+=1
  else:
   month['observed_count']+=1
   if first:month['first_observed_session']=row['session']
  projection.append(dict(input_row=t,monthly_coordinate=first,first_actual_observed_session=month['first_observed_session'],seal_outcome_used_to_select_coordinate=False))
 equal(e['complete_typed_rows'],typed);equal(e['known_typed_rows_preserved'],typed)
 equal(policy['projection_inputs']['known_rows'],typed);equal(e['projection'],projection);equal(e['months'],list(months.values()))
 assert sum(p['monthly_coordinate'] for p in projection)==3 and months['2026-10']['first_observed_session'] is None
 equal(d['original_capture_plan_preserved'],capture['plan'])
 equal(d['current_capture_interval'],dict(start=capture['capture_started_at_utc'],end=capture['observed_at_utc']))
 start=datetime.fromisoformat(capture['capture_started_at_utc']);end=datetime.fromisoformat(capture['observed_at_utc']);assert start<=end and end.isoformat()=='2026-10-02T15:21:18.150888+00:00'
 equal(e['capture_reference'],refs['capture']);equal(e['clock_evidence_preserved'],dict(seal_evaluation_at_utc=None,tzif_reference=capture['captured_artifacts']['tzif']))
 source_dates={}
 for ticker in ('QQQ','SPY'):
  r=capture['captured_artifacts'][ticker];b=Path(r['path']).read_bytes();assert sha(b)==r['sha256']==sources[r['path']]
  rows=list(csv.DictReader(io.StringIO(b.decode('utf-8-sig'))));source_dates[ticker]=[r['Date'] for r in rows if r['Date']>=typed[0]['session']]
  equal(source_dates[ticker],[r['session'] for r in typed])
 expected_sources=dict(coverage_reference=dict(refs['capture'],json_pointer='/plan/csv_scope_evidence'),references=list(refs.values()),complete_source_session_dates=source_dates,revisions=capture['plan']['capture_plan']['revisions'])
 # Input-reference object serialization sorts keys, while the saved list retains BOUND order.
 observed=e['source_references_preserved'];equal(observed['coverage_reference'],expected_sources['coverage_reference'])
 equal(observed['complete_source_session_dates'],source_dates);equal(observed['revisions'],[])
 equal(sorted(observed['references'],key=lambda r:r['path']),sorted(refs.values(),key=lambda r:r['path']))
 claims={r['path']:r['sha256'] for r in refs.values()};tz=capture['captured_artifacts']['tzif'];claims[tz['path']]=tz['sha256'];equal(e['source_hash_claims'],claims)
 assert e['status']=='BLOCKED' and e['policy_id']=='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
 equal(e['reasons'],['NO_NEW_OBSERVATION_EVIDENCE','NO_DECISION_REQUESTED']);equal(e['new_observation_evidence_preserved'],[])
 for k in ('selected_row','decision_session','monthly_coordinate','original_seal_status','timing_status'):assert e[k] is None
 assert e['observation_evidence_status']=='NO_NEW_OBSERVATION_EVIDENCE'
 started=json.loads((OUT/'started.json').read_bytes());equal(started['source_hashes'],sources);equal(started['input_references'],refs)
 false_outer=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','oos_recovery_completed','old_calendar_mutated','old_generator_called','new_observation_receipt_created','production_lineage_ready','network_capture_performed','old_audit_repeated','gap_ledger_validation_reexecuted','full_transitive_source_closure_reverified','fresh_observation')
 for k in false_outer:assert d[k] is pub[k] is started[k] is False
 for k in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','oos_recovery_completed','source_evidence_authenticated','observation_receipt_authenticated','authentic_clock_verified','exchange_holidays_verified','early_closes_verified','old_calendar_mutated','old_generator_called','new_observation_receipt_created','production_lineage_ready','calendar_prerequisites_conditionally_satisfied'):assert e[k] is False
 for path,h in sources.items():assert sha(Path(path).read_bytes())==h
 assert sha((OUT/'evidence.json').read_bytes())==RESULT and sha((OUT/'publication.json').read_bytes())==PUB
 return dict(schema='GAP_CANDIDATE_ADAPTER_INDEPENDENT_READBACK_V1',status='PASS',evidence_sha256=RESULT,publication_sha256=PUB,reader_sha256=sha(Path(__file__).read_bytes()),direct_sources=len(sources),typed_rows=65,old_unknown_rows=60,missed_rows=5,months=list(months.values()),historical_monthly_coordinates=3,new_observations=0,new_candidates=0,capture_interval=d['current_capture_interval'],producer_called=False,parent_audit_repeated=False,point_in_time_verified=False,production_lineage_ready=False)

if __name__=='__main__':
 result=run();stem=ROOT/'DYNAMIC_GAP_CANDIDATE_ADAPTER_INDEPENDENT_READBACK_20261003'
 with stem.with_suffix('.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
 report=f'''# Gap candidate adapter 独立实际读回

结论：PASS。新产物 `{RESULT}`；publication `{PUB}`。读回脚本 SHA `{result['reader_sha256']}`。

独立核验 18 直接来源 SHA、11 输入引用与回执、65 连续类型行、全部行指针及月首投影。保留 60 个旧实际观察（seal UNKNOWN）和 5 个缺口；7/8/9 月共 3 个历史月首，10 月只有缺口，首次实际观察仍为空。新增观察 0、候选 0，状态 BLOCKED。

当前 capture 起止为 {result['capture_interval']['start']} 至 {result['capture_interval']['end']}；原样保留，没有变成实际新观察或封存时钟。两个 CSV 自首记账日起均为同一 65 日期；所有权限 False。核验保存的来源引用和投影，不重新执行父 capture、gap 或 monthly 审计，不核行情数值、不创建 observation receipt、不补回 OOS。
'''
 with stem.with_suffix('.md').open('x',encoding='utf-8') as f:f.write(report)
 print(json.dumps(result,ensure_ascii=False))
