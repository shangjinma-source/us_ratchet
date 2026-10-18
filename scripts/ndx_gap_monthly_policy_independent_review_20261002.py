"""Independent saved monthly policy coordinates; no production imports."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/cache/research/gap_monthly_policy_20261002_v1'
RESULT='d04c7cd9181eb5585c7ddbd880b02947ec135552944a6f90b5e1fd39bb21b946'
PUB='23af1d2798f4c7d5e33142a97319dead34a533606b98304da7b7c9deeb65f76d'
POLICY='FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
PINS={'frontier':'a463539f706db1925c52cab0f8d1a4da34eb36b62e915b1842e9cbe229062170','publication':'36c99f365a545f3c508795a8a1db39ed9afcddf4120dd4aa7ad73ad1b50abe44','user_choice':'f661616a86dca8e80aa3e8bcea1b55c29b97760e993948049327fe1a38d84906','core':'aab44a1cd8c41be42ace2061b788865d90f83e9c678f6daa59560809edfc7e1b'}
FLAGS=('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','oos_recovery_completed','old_calendar_mutated','old_generator_modified','existing_frontier_rewritten','full_transitive_source_closure_reverified','input_timeliness_verified','old_calendar_full_validation_reexecuted')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,digest):
 raw=Path(path).read_bytes();assert sha(raw)==digest;return json.loads(raw)
def canon(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def run():
 result=load(OUT/'policy.json',RESULT);pub=load(OUT/'publication.json',PUB)
 assert {p.name for p in OUT.iterdir()}=={'started.json','policy.json','publication.json'}
 assert pub['schema']=='GAP_MONTHLY_POLICY_PUBLICATION_V1' and pub['status']=='PUBLISHED_USER_SELECTED_POLICY_COORDINATES_NO_SEAL'
 assert pub['policy_reference']==dict(path=str(OUT/'policy.json'),sha256=RESULT)
 sources=result['source_hashes'];refs=result['input_references'];assert len(sources)==5 and set(refs)==set(PINS) and pub['source_hashes']==sources
 for path,digest in sources.items():assert sha(Path(path).read_bytes())==digest
 for role,digest in PINS.items():assert refs[role]['sha256']==digest and sources[refs[role]['path']]==digest
 choice=Path(refs['user_choice']['path']).read_text(encoding='utf-8-sig')
 assert '> 按首次实际观察延续：缺口不占月首机会（更贴近原合同）' in choice and POLICY in choice
 assert '不声称密码学用户签名' in choice
 frontier=load(refs['frontier']['path'],PINS['frontier']);receipt=load(refs['publication']['path'],PINS['publication'])
 assert receipt['frontier_reference']==refs['frontier'] and receipt['source_hashes']==frontier['source_hashes']
 rows=frontier['known_accounted_rows'];assert len(rows)==65 and result['saved_frontier_rows']==rows
 assert result['schema']=='SOURCE_BOUND_GAP_MONTHLY_POLICY_PROJECTION_V1' and result['policy_id']==POLICY
 assert result['user_choice_reference']==refs['user_choice'] and result['frontier_reference']==refs['frontier']
 assert result['user_choice_recorded_from_explicit_reply'] is True and result['cryptographic_user_signature_claimed'] is False
 assert result['preserved_old_frontier_month_semantics']==frontier['month_first_semantics']=='UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE'
 typed=[]; projected=[];months={};old_coordinates=0
 for i,row in enumerate(rows):
  gap=i>=60;assert row['kind']==('MISSED_OBSERVATION' if gap else 'SEALED_PARENT_OBSERVED_SESSION')
  t=dict(sequence=i+1,session=row['session'],kind=row['kind'],evidence_reference=dict(refs['frontier'],json_pointer=f'/known_accounted_rows/{i}'),seal_status='NOT_ATTEMPTED' if gap else 'UNKNOWN');typed.append(t)
  month=row['session'][:7];s=months.setdefault(month,dict(month=month,first_observed_session=None,observed_count=0,missed_count=0))
  eligible=not gap and s['first_observed_session'] is None
  if gap:s['missed_count']+=1
  else:
   s['observed_count']+=1
   if eligible:s['first_observed_session']=row['session'];old_coordinates+=1
  projected.append(dict(input_row=t,monthly_coordinate_eligible=eligible,month_first_observed_session_as_of_row=s['first_observed_session'],seal_outcome_used_to_select_coordinate=False,candidate_seal_allowed=False,cohort_registration_allowed=False))
 assert canon(result['projection_inputs'])==canon(dict(policy_id=POLICY,known_rows=typed,new_prospective_observations=[]))
 p=result['projection'];assert p['schema']=='GAP_MONTHLY_OBSERVATION_POLICY_RESEARCH_V1' and p['policy_id']==POLICY
 assert canon(p['rows'])==canon(projected) and canon(p['months'])==canon(list(months.values()))
 assert len(months)==4 and old_coordinates==3 and months['2026-10']==dict(month='2026-10',first_observed_session=None,observed_count=0,missed_count=1)
 assert type(p['known_row_count']) is int and p['known_row_count']==65
 for value in (p['new_prospective_observation_count'],result['new_observation_count'],result['prospective_monthly_coordinate_count']):assert type(value) is int and value==0
 assert result['prospective_decision_not_before']=='2026-10-01'
 assert p['caller_source_evidence_not_verified'] is True
 for key in ('complete_sequence_independently_verified','input_timeliness_verified','user_choice_authenticity_verified','candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed','oos_recovery_completed'):assert p[key] is False
 started=json.loads((OUT/'started.json').read_bytes());assert started['source_hashes']==sources and started['retry_allowed'] is False
 for key in FLAGS:assert result[key] is pub[key] is started[key] is False
 for path,digest in sources.items():assert sha(Path(path).read_bytes())==digest
 assert sha((OUT/'policy.json').read_bytes())==RESULT and sha((OUT/'publication.json').read_bytes())==PUB
 return dict(typed_rows=65,unknown_old_seal_status_rows=60,gap_not_attempted_rows=5,months=list(months.values()),historical_coordinates=old_coordinates,prospective_coordinates=0,direct_sources=5,production_projection_called=False)
if __name__=='__main__':print(json.dumps(run(),indent=2))
