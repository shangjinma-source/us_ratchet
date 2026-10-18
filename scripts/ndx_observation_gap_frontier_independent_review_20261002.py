"""Independent saved frontier projection readback, no production imports."""
from pathlib import Path
import csv,io,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/cache/research/observation_gap_frontier_20261002_v1'
SHA='a463539f706db1925c52cab0f8d1a4da34eb36b62e915b1842e9cbe229062170'
PUB='36c99f365a545f3c508795a8a1db39ed9afcddf4120dd4aa7ad73ad1b50abe44'
PIN={'ledger':'8c15643e8ccf0b4356f235b43bb29152d98be2c9e71c3f16310f6a1d7d12e67d','publication':'6d36f4e420dd4fe959c1d88cb3b68b133ccce57ed6ad316b9d99ba1b7e411d7d','parent_sessions':'f78183b85d8e83b5037d3c4b77b2a8662af451def7a0411bbc26f82e1081f2e2','QQQ':'a05d32edf48d035631deffe86e4cb157ffd6918c285b23cdc5a02c3677756c88','SPY':'dcbae9b32cd04edb78b6b334f9c703a224d9b5ed00658c925a19f2e2e6e2c6cf','core':'6588c37907a281012c4573337a6ea1261db6ad869835758c4cd8347a9d33feaf'}
FALSE=('observed_session_added','fresh_observation','decision_eligible','candidate_seal_allowed','cohort_registration_allowed','first_observed_session_of_month','historical_timeliness_verified','future_timeliness_granted','canonical_calendar_append_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','source_bytes_verified','system_clock_verified','oos_recovery_completed','gap_hash_chain_reverified','parent_calendar_reverified')
WRAPPER_FALSE=('old_calendar_mutated','old_calendar_full_validation_reexecuted','gap_ledger_validation_reexecuted','classifier_reexecuted','gap_append_called','candidate_generator_called','timeliness_evaluated','canonical_calendar_append_allowed','candidate_seal_allowed','cohort_registration_allowed','oos_recovery_completed','source_price_rows_validated_for_execution','promotion_allowed','live_mutation_allowed','point_in_time_verified','full_transitive_source_closure_reverified')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,digest):
 raw=Path(path).read_bytes();assert sha(raw)==digest;return json.loads(raw)
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def dates(raw,key):
 rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))));return [r[key] for r in rows]
def run():
 result=load(OUT/'frontier.json',SHA);pub=load(OUT/'publication.json',PUB)
 assert {p.name for p in OUT.iterdir()}=={'started.json','frontier.json','publication.json'}
 assert pub['status']=='PUBLISHED_ACCOUNTED_FRONTIER_ONLY_NO_ELIGIBILITY' and pub['schema']=='OBSERVATION_GAP_FRONTIER_PUBLICATION_V1'
 assert pub['frontier_reference']==dict(path=str(OUT/'frontier.json'),sha256=SHA)
 sources=result['source_hashes'];refs=result['input_references'];assert len(sources)==7 and set(refs)==set(PIN) and pub['source_hashes']==sources
 for path,digest in sources.items():assert sha(Path(path).read_bytes())==digest
 raw={}
 for role,digest in PIN.items():
  ref=refs[role];assert ref['sha256']==digest and sources[ref['path']]==digest
  raw[role]=Path(ref['path']).read_bytes();assert sha(raw[role])==digest
 parent=dates(raw['parent_sessions'],'session_date');ledger=json.loads(raw['ledger']);receipt=json.loads(raw['publication'])
 assert receipt['artifacts']['ledger']==refs['ledger'] and receipt['artifacts']['parent_sessions']==refs['parent_sessions']
 assert ledger['parent_binding']['session_projection_reference']==receipt['input_references']['parent_sessions']
 assert ledger['parent_binding']['session_projection_reference']['sha256']==PIN['parent_sessions']
 assert len(parent)==60 and parent==sorted(set(parent)) and parent[-1]=='2026-09-24'
 common=None;counts={}
 for ticker in ('QQQ','SPY'):
  seq=dates(raw[ticker],'Date');assert seq==sorted(set(seq));counts[ticker]=len(seq)
  assert receipt['input_references'][ticker]==refs[ticker]==ledger['batches'][0]['classification_capture']['captured_source_references'][ticker]
  common=set(seq) if common is None else common & set(seq)
 common=sorted(d for d in common if d>=parent[0]);gap=[r['session'] for r in ledger['events']]
 assert gap==['2026-09-25','2026-09-28','2026-09-29','2026-09-30','2026-10-01'] and common==parent+gap and len(common)==65
 expected=[dict(session=d,kind='SEALED_PARENT_OBSERVED_SESSION',parent_session_index=i,eligibility_reverified=False) for i,d in enumerate(parent)]
 expected += [dict(session=e['session'],kind='MISSED_OBSERVATION',gap_event_index=i,gap_event_sha256=e['event_sha256'],counts_as_observed_session=False,decision_eligible=False) for i,e in enumerate(ledger['events'])]
 assert canonical(result['known_accounted_rows'])==canonical(expected)
 assert result['last_observed_session']=='2026-09-24' and result['last_accounted_gap_session']==result['last_accounted_session']=='2026-10-01'
 assert type(result['parent_observed_session_count']) is int and result['parent_observed_session_count']==60
 assert type(result['accounted_gap_count']) is int and result['accounted_gap_count']==5
 assert result['unaccounted_source_dates']==[] and result['excluded_source_dates_before_parent_start']==[] and result['raw_source_date_counts']==counts
 assert result['month_first_semantics']=='UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE'
 assert result['unaccounted_dates_require_clock_price_and_revision_review'] is True and result['scope']=='CURSOR_PLANNING_ONLY_NOT_OOS_RECOVERY'
 for key in FALSE:assert result[key] is False
 started=json.loads((OUT/'started.json').read_bytes());assert started['source_hashes']==sources and started['retry_allowed'] is False
 for key in WRAPPER_FALSE:assert result[key] is pub[key] is started[key] is False
 for key in ('observed_session_increment','fresh_session_increment','seal_increment','cohort_increment'):assert type(result[key]) is int and result[key]==0
 for path,digest in sources.items():assert sha(Path(path).read_bytes())==digest
 assert sha((OUT/'frontier.json').read_bytes())==SHA and sha((OUT/'publication.json').read_bytes())==PUB
 return dict(typed_rows=65,parent_observed_rows=60,missed_rows=5,unaccounted=0,last_observed='2026-09-24',last_accounted='2026-10-01',direct_sources=7,raw_date_counts=counts,old_audits_called=False,production_functions_called=False)
if __name__=='__main__':print(json.dumps(run(),indent=2))
