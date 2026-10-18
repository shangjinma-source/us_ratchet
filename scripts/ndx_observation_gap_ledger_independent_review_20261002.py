"""Independent saved gap-chain readback; no production/calendar imports."""
from pathlib import Path
from datetime import datetime
import csv,io,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/cache/research/observation_gap_ledger_20261002_v1'
LEDGER_SHA='8c15643e8ccf0b4356f235b43bb29152d98be2c9e71c3f16310f6a1d7d12e67d'
PUB_SHA='6d36f4e420dd4fe959c1d88cb3b68b133ccce57ed6ad316b9d99ba1b7e411d7d'
DATES=['2026-09-25','2026-09-28','2026-09-29','2026-09-30','2026-10-01']
FALSE=dict.fromkeys(('observed_session_added','fresh_observation','decision_eligible','candidate_seal_allowed','cohort_registration_allowed','first_observed_session_of_month','historical_timeliness_verified','future_timeliness_granted','canonical_calendar_append_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','source_bytes_verified','system_clock_verified','oos_recovery_completed'),False)
PUB_FALSE=('old_calendar_mutated','old_calendar_full_validation_reexecuted','classifier_reexecuted','canonical_calendar_append_allowed','candidate_seal_allowed','cohort_registration_allowed','oos_recovery_completed','source_price_rows_validated_for_execution','promotion_allowed','live_mutation_allowed','point_in_time_verified','full_transitive_source_closure_reverified')
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def load(p,h):
 b=Path(p).read_bytes();assert sha(b)==h;return json.loads(b)
def run():
 ledger=load(OUT/'ledger.json',LEDGER_SHA);pub=load(OUT/'publication.json',PUB_SHA)
 assert {p.name for p in OUT.iterdir()}=={'started.json','publication.json','ledger.json','extension_events.jsonl','parent_manifest.json','parent_events.jsonl','parent_sessions.csv','parent_receipt.json'}
 assert pub['schema']=='OBSERVATION_GAP_LEDGER_PUBLICATION_V1' and pub['status']=='PUBLISHED_MISSED_OBSERVATION_EVIDENCE_ONLY'
 sources=pub['source_hashes'];refs=pub['input_references'];assert len(sources)==9 and len(refs)==8
 raw={}
 for p,h in sources.items():assert sha(Path(p).read_bytes())==h
 for role,ref in refs.items():
  assert sources[ref['path']]==ref['sha256'];raw[role]=Path(ref['path']).read_bytes();assert sha(raw[role])==ref['sha256']
 for key in PUB_FALSE:assert pub[key] is False
 artifacts=pub['artifacts'];assert len(artifacts)==6
 for role,ref in artifacts.items():assert sha(Path(ref['path']).read_bytes())==ref['sha256']
 assert artifacts['ledger']==dict(path=str(OUT/'ledger.json'),sha256=LEDGER_SHA)
 for role,name in [('parent_manifest','parent_manifest.json'),('parent_events','parent_events.jsonl'),('parent_sessions','parent_sessions.csv'),('parent_receipt','parent_receipt.json')]:
  assert artifacts[role]==dict(path=str(OUT/name),sha256=refs[role]['sha256']) and (OUT/name).read_bytes()==raw[role]
 manifest=json.loads(raw['parent_manifest']);receipt=json.loads(raw['parent_receipt']);capture=json.loads(raw['classification'])
 assert receipt['planned_manifest']==manifest and receipt['transaction_id']==manifest['commit_transaction_id']
 oldevents=[json.loads(l) for l in raw['parent_events'].splitlines()];sessions=list(csv.DictReader(io.StringIO(raw['parent_sessions'].decode('utf-8-sig'))))
 assert len(oldevents)==manifest['event_count']==66 and len(sessions)==manifest['session_count']==60
 assert oldevents[-1]['event_sha256']==manifest['latest_event_sha256']
 assert manifest['latest_session_date']==sessions[-1]['session_date']=='2026-09-24' and manifest['decision_eligible_session_count']==0
 assert manifest['artifacts']['event_ledger']['sha256']==refs['parent_events']['sha256'] and manifest['artifacts']['session_projection']['sha256']==refs['parent_sessions']['sha256']
 expected_parent=dict(manifest_reference=refs['parent_manifest'],event_prefix_reference=refs['parent_events'],session_projection_reference=refs['parent_sessions'],event_count=66,session_count=60,last_session='2026-09-24',event_tail_sha256=manifest['latest_event_sha256'])
 assert ledger['parent_binding']==expected_parent
 recorded=pub['recorded_at_utc'];assert recorded=='2026-10-02T14:58:49.580728+00:00'
 started=json.loads((OUT/'started.json').read_bytes());assert started['recorded_at_utc']==recorded and started['source_hashes']==sources and started['retry_allowed'] is False
 for k in PUB_FALSE:assert started[k] is False
 assert ledger['batches']==[dict(classification_capture=capture,classification_reference=refs['classification'],recorded_at_utc=recorded)]
 assert capture['captured_using_system_clock'] is True and datetime.fromisoformat(recorded)>=datetime.fromisoformat(capture['captured_at_utc'])
 assert capture['parent_references']['calendar_manifest']==refs['parent_manifest'] and capture['parent_references']['calendar_events']==refs['parent_events']
 classification=capture['classification'];assert classification['observed_at_utc']==capture['captured_at_utc'] and classification['last_sealed_session']=='2026-09-24'
 assert classification['timeliness_candidate'] is None and classification['missed_or_ineligible_row_count']==5
 assert [r['session'] for r in classification['pending_classifications']]==DATES
 indexed={}
 for ticker in ('QQQ','SPY'):
  assert capture['captured_source_references'][ticker]==refs[ticker]
  rows=list(csv.DictReader(io.StringIO(raw[ticker].decode('utf-8-sig'))));dates=[r['Date'] for r in rows];assert dates==sorted(set(dates))
  indexed[ticker]={r['Date']:r for r in rows};assert capture['pending_source_rows'][ticker]=={d:indexed[ticker][d] for d in DATES}
 previous=manifest['latest_event_sha256'];expected_events=[]
 for i,row in enumerate(classification['pending_classifications']):
  assert row['recorded_at_utc']==capture['captured_at_utc'] and row['decision_eligible'] is False and row['first_observed_at_historical_close_claimed'] is False
  assert datetime.fromisoformat(row['conservative_close_utc'])<datetime.fromisoformat(row['conservative_seal_deadline_utc'])<=datetime.fromisoformat(capture['captured_at_utc'])
  assert row['classification']==('EARLIER_PENDING_ROW_NOT_TIMELY_EVIDENCE' if i<4 else 'LATEST_ROW_SEAL_DEADLINE_MISSED')
  event=dict(schema='MISSED_OBSERVATION_EVIDENCE_EVENT_V1',event_sequence=67+i,event_type='MISSED_OBSERVATION',session=DATES[i],event_recorded_at_utc=recorded,classification_captured_at_utc=capture['captured_at_utc'],historical_source_first_observed_at_utc=None,classification_reference=refs['classification'],classification_json_pointer='/classification/pending_classifications/'+str(i),classification_row=row,source_references=capture['captured_source_references'],saved_source_rows={t:indexed[t][DATES[i]] for t in indexed},previous_event_sha256=previous,**FALSE)
  event['event_sha256']=sha(canonical(event));previous=event['event_sha256'];expected_events.append(event)
 assert canonical(ledger['events'])==canonical(expected_events)
 assert (OUT/'extension_events.jsonl').read_bytes()==b''.join(canonical(e)+b'\n' for e in expected_events)
 expected=dict(schema='OBSERVATION_GAP_EVIDENCE_LEDGER_V1',parent_binding=expected_parent,batches=ledger['batches'],events=expected_events,missed_observation_count=5,terminal_event_sha256=previous,observed_session_increment=0,fresh_session_increment=0,seal_increment=0,cohort_increment=0,old_last_observed_session_unchanged='2026-09-24',scope='SEPARATE_MISSED_EVIDENCE_CHAIN_NOT_CALENDAR_V2_OR_CANDIDATE_ADAPTER',**FALSE)
 expected['ledger_sha256']=sha(canonical(expected));assert canonical(ledger)==canonical(expected)
 for p,h in sources.items():assert sha(Path(p).read_bytes())==h
 assert sha((OUT/'ledger.json').read_bytes())==LEDGER_SHA and sha((OUT/'publication.json').read_bytes())==PUB_SHA
 return dict(events=5,sequences=[67,71],parent_copy_count=4,parent_events_unchanged=66,parent_sessions_unchanged=60,direct_sources=9,quoted_csv_rows=10,captured_at_utc=capture['captured_at_utc'],recorded_at_utc=recorded,observed_increment=0,fresh_increment=0,seal_increment=0,cohort_increment=0,production_function_called=False)
if __name__=='__main__':print(json.dumps(run(),indent=2))
