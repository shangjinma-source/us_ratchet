"""Real small DataFrame integration; no seal, writer, account, network or raw IO."""
from copy import deepcopy
from datetime import date,timedelta
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import unittest
from backtest import ndx_persisted_fresh_snapshot_executor_research as m

def ref(name):return dict(path=str(m.ROOT/'tmp'/('synthetic-'+name)),sha256=sha256(name.encode()).hexdigest())
def projection(rows,reference):return dict(rows=rows,source_reference=reference,projection_sha256=m.digest(rows),metadata_preserved={'scope':'SYNTHETIC_NO_AUTHORITY','corporate_actions':[]})
def fixture(version='first'):
 flags={k:False for k in ('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed')}
 obs={k:ref(k)for k in ('payload_reference','receipt_reference','audit_reference','reader_reference')};oid='a'*64
 refs={k:ref('calendar-'+k)for k in ('reference','publication_reference','readback_reference','reader_reference')}
 rows=[];d=date(2026,7,3)
 while len(rows)<66:
  if d.weekday()<5:rows.append(dict(sequence=len(rows)+1,session=d.isoformat(),kind='PROSPECTIVE_OBSERVED_SESSION'if len(rows)==65 else'SEALED_PARENT_OBSERVED_SESSION'if len(rows)<60 else'MISSED_OBSERVATION',seal_status='NOT_ATTEMPTED'))
  d+=timedelta(days=1)
 evidence=dict(schema='FIRST_PERSISTED_OBSERVATION_CANDIDATE_CALENDAR_SNAPSHOT_EVIDENCE_V1',adapter_schema='FIRST_V1_SCOPED_SNAPSHOT_EQUIVALENCE_BRIDGE_V1',status='CONDITIONAL_CALENDAR_PREREQUISITES_ONLY',calendar_prerequisites_conditionally_satisfied=True,monthly_coordinate=True,reasons=[],original_seal_status='NOT_ATTEMPTED',later_observed_sessions=[],selected_observation_id=oid,input_references=dict(observation=obs),known_typed_rows_preserved=rows,selected_existing_row=deepcopy(rows[-1]),lineage_blockers=['SEAL_STATUS_EVENT_HISTORY_NOT_BOUND','NEW_CANDIDATE_GENERATOR_AND_COHORT_CONSUMER_NOT_BOUND'],timing=dict(publication_check='2026-10-02T20:02:00+00:00',seal_evaluation_at_utc='2026-10-02T20:03:00+00:00',conservative_close_utc='2026-10-02T20:00:00+00:00',conservative_deadline_utc='2026-10-05T13:30:00+00:00'),**flags)
 doc=dict(schema='SOURCE_BOUND_FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_V1',adapter_schema=evidence['adapter_schema'],evidence=evidence,source_hashes={},**flags)
 pub=dict(schema='FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_PUBLICATION_V1',adapter_schema=evidence['adapter_schema'],status='PUBLISHED_CONDITIONAL_EVIDENCE_NOT_SEAL_AUTHORITY',result_reference=refs['reference'],source_hashes={},**flags)
 audit=dict(schema='FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_INDEPENDENT_READBACK_V1',status='PASS',result_reference=refs['reference'],publication_reference=refs['publication_reference'],reader_sha256=refs['reader_reference']['sha256'],source_hashes={r['path']:r['sha256']for r in refs.values()},**flags)
 if version=='later':
  doc['schema']='SOURCE_BOUND_PERSISTED_CANDIDATE_CALENDAR_V2';pub['schema']='PERSISTED_CANDIDATE_CALENDAR_PUBLICATION_V2';audit['schema']='PERSISTED_CANDIDATE_CALENDAR_INDEPENDENT_READBACK_V2';evidence['schema']='PERSISTED_OBSERVATION_CANDIDATE_CALENDAR_EVIDENCE_V2'
  for obj in (doc,pub,evidence):del obj['adapter_schema']
 if version=='later':
  rows.append(dict(sequence=67,session='2026-11-02',kind='PROSPECTIVE_OBSERVED_SESSION',seal_status='NOT_ATTEMPTED'));evidence['selected_existing_row']=deepcopy(rows[-1]);evidence['timing']={k:v.replace('2026-10-02T20:','2026-11-02T21:').replace('2026-10-05T13:30','2026-11-03T14:30')for k,v in evidence['timing'].items()}
 selected_date=evidence['selected_existing_row']['session']
 calendar=dict(refs,document=doc,publication=pub,readback=audit)
 roles={k:ref(k)for k in m.ROLES};roles['generator_contract']=dict(path=str(m.CONTRACT),sha256=m.CONTRACT_SHA);roles['membership_scope']=dict(path=str(m.SCOPE),sha256=m.SCOPE_SHA)
 dates=[];d=date.fromisoformat(selected_date)
 while len(dates)<300:
  if d.weekday()<5:dates.append(d.isoformat())
  d-=timedelta(days=1)
 dates.reverse();tickers=[f'T{i:02d}'for i in range(8)]
 membership=[dict(selection_date=selected_date,ticker=t,security_id='security:'+t,issuer_id='issuer:'+('shared'if i<2 else t),risk_chain='oil_gas'if i==2 else'semiconductor',membership_status='VERIFIED_POINT_IN_TIME_MEMBER',membership_effective_from='2026-08-28',membership_effective_to=None,evidence_available_timestamp_utc='2026-09-01T00:00:00+00:00',membership_evidence_reference=roles['membership'])for i,t in enumerate(tickers[:4])]
 adjusted={t:projection([dict(Date=d,Close=100.0+i+n/100)for n,d in enumerate(dates)],roles['adjusted_prices'])for i,t in enumerate(tickers)}
 nominal={t:projection([dict(Date=d,Close=100.0+i+n/100,Volume=1000000.0)for n,d in enumerate(dates)],roles['nominal_prices'])for i,t in enumerate(tickers)}
 x=dict(schema=m.INPUT_SCHEMA,observation_id=oid,observation_references=obs,calendar=calendar,candidate_data_references=roles,input_versions={k:r['sha256']for k,r in roles.items()},input_references=deepcopy(roles),generator_contract_bytes=m.CONTRACT.read_bytes(),membership_scope_bytes=m.SCOPE.read_bytes(),expected_membership_security_ids=[r['security_id']for r in membership],eligible_membership=projection(membership,roles['membership']),adjusted_prices=adjusted,nominal_prices=nominal,target_nav=projection([dict(Date=d,Close=1.0+n/1000)for n,d in enumerate(dates)],roles['target_nav']),frozen_original8_tickers=tickers,evidence_sidecars={k:dict(reference=r,original_evidence={'scope':'SYNTHETIC_CALLER_SUPPLIED_NOT_AUTHENTICATED'})for k,r in roles.items()})
 registration=dict(schema='OBSERVATION_CANDIDATE_EXECUTOR_REGISTRATION_V1',entry_point=m.ENTRY,operation='FRESH_INPUT_SNAPSHOT_ONLY',executor_reference=dict(path=str(m.SOURCE),sha256=sha256(m.SOURCE.read_bytes()).hexdigest()),computation_reference=dict(path=str(m.COMPUTATION),sha256=m.COMPUTATION_SHA),versioning_reference=dict(path=str(m.VERSIONING),sha256=m.VERSIONING_SHA),generator_contract_reference=roles['generator_contract'],membership_scope_reference=roles['membership_scope'],input_schema=m.INPUT_SCHEMA,output_schema=m.OUTPUT_SCHEMA)
 return dict(execution_input=x,registration=registration,execution_started_at_utc='2026-10-02T20:04:00+00:00'if version=='first'else'2026-11-02T21:04:00+00:00')

class Tests(unittest.TestCase):
 def test_all_ndx_nontech_share_classes_missing_risk_and_unknown_are_explicit(self):
  a=fixture();out=m.execute_fresh_input_snapshot(**a)
  self.assertEqual({r['risk_chain']for r in out['snapshot']['eligible_securities']['rows']},{'oil_gas','semiconductor'})
  self.assertEqual(out['universe_denominators'][0]['security_count'],4);self.assertEqual(out['universe_denominators'][0]['issuer_count'],3)
  self.assertEqual(out['planned_evaluation_tracks'],['continuous','whole_lot']);self.assertFalse(out['industry_filter_applied']);self.assertFalse(out['complete_universe_verified'])
  p=a['execution_input']['eligible_membership'];p['rows'][0]['risk_chain']=None;p['rows'][1]['membership_status']='UNKNOWN';p['projection_sha256']=m.digest(p['rows'])
  out=m.execute_fresh_input_snapshot(**a);self.assertEqual(out['snapshot']['risk_validation_blockers'][0]['security_id'],'security:T00');self.assertEqual(out['snapshot']['exclusions'][0]['reasons'],['MEMBERSHIP_UNKNOWN']);self.assertEqual(len(out['snapshot']['full_membership_inventory_preserved']),4)
 def test_bool_nonfinite_calendar_and_legacy_track_fail_before_numeric_helpers(self):
  for mode in ('adjusted','volume','nav','calendar','legacy'):
   a=fixture();x=a['execution_input']
   if mode=='calendar':x['calendar']['document']['evidence']['known_typed_rows_preserved'][0]['session']='2026-00-01'
   elif mode=='legacy':
    p=x['eligible_membership'];p['rows'][0]['universe_track']='strict_technology';p['projection_sha256']=m.digest(p['rows'])
   else:
    p=x['target_nav']if mode=='nav'else x['nominal_prices']['T00']if mode=='volume'else x['adjusted_prices']['T00'];p['rows'][0]['Volume'if mode=='volume'else'Close']=True;p['projection_sha256']=m.digest(p['rows'])
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.execute_fresh_input_snapshot(**a)
 def test_real_frozen_computation_both_calendars_full_k_no_writes(self):
  for version in ('first','later'):
   a=fixture(version);before=deepcopy(a)
   with patch.object(Path,'write_bytes',side_effect=AssertionError('No writer')),patch.object(Path,'write_text',side_effect=AssertionError('No writer')):out=m.execute_fresh_input_snapshot(**a)
   self.assertEqual(a,before);self.assertEqual(len(out['snapshot']['training_adjusted_close']['rows']),300)
   self.assertEqual([d['theoretical_security_combination_count']for d in out['universe_denominators']],[11]);self.assertEqual([j['theoretical_security_combinations']for j in out['snapshot']['job_plan']['rows']],[4,5,2])
   self.assertEqual([j['holding_count']for j in out['snapshot']['job_plan']['rows']],[1,2,3]);self.assertEqual(out['snapshot']['execution_date'],None)
   self.assertTrue(all(out[k]is False for k in m.FLAGS));self.assertEqual(out['calendar_evidence_preserved']['lineage_blockers'],before['execution_input']['calendar']['document']['evidence']['lineage_blockers'])
 def test_incomplete_registration_roles_and_calendar_block_before_computation(self):
  for mode in ('callable','role','calendar','authority','deadline','version','contract'):
   a=fixture();x=a['execution_input'];e=x['calendar']['document']['evidence']
   if mode=='callable':a['registration']['entry_point']='caller.function'
   elif mode=='role':del x['candidate_data_references']['corporate_actions']
   elif mode=='calendar':e['status']='BLOCKED'
   elif mode=='authority':e['candidate_seal_allowed']=0
   elif mode=='deadline':a['execution_started_at_utc']='2026-10-05T13:30:00+00:00'
   elif mode=='version':x['calendar']['readback']['schema']='PERSISTED_CANDIDATE_CALENDAR_INDEPENDENT_READBACK_V2'
   else:x['generator_contract_bytes']+=b'\n'
   with patch.object(m,'fixed_computation',side_effect=AssertionError('Must fail before compute')),self.subTest(mode=mode),self.assertRaises((ValueError,KeyError)):m.execute_fresh_input_snapshot(**a)
 def test_future_identity_and_missing_decision_prices_use_frozen_gates(self):
  for mode in ('future','missing_close','projection'):
   a=fixture();x=a['execution_input']
   if mode=='future':
    p=x['eligible_membership'];p['rows'][0]['evidence_available_timestamp_utc']='2026-10-03T00:00:00+00:00';p['projection_sha256']=m.digest(p['rows'])
   elif mode=='missing_close':
    p=x['adjusted_prices']['T00'];p['rows'].pop();p['projection_sha256']=m.digest(p['rows'])
   else:x['nominal_prices']['T00']['rows'][0]['Close']=2
   with self.subTest(mode=mode):
    if mode=='projection':
     with self.assertRaises(ValueError):m.execute_fresh_input_snapshot(**a)
    else:
     out=m.execute_fresh_input_snapshot(**a);self.assertTrue(out['snapshot']['exclusions'])
     if mode=='missing_close':self.assertEqual(out['status'],'BLOCKED_INPUT_REQUIREMENTS_NO_SNAPSHOT')
 def test_original_evidence_preserved_and_no_serialization_fabrication(self):
  a=fixture();a['execution_input']['evidence_sidecars']['target_currency']['original_evidence']={'currency':'CNY','historical_currency_verified':False};out=m.execute_fresh_input_snapshot(**a)
  self.assertEqual(out['evidence_sidecars_preserved'],a['execution_input']['evidence_sidecars'])
  module=m.fixed_computation()
  for value in (object(),float('nan'),float('inf')):
   with self.assertRaises(ValueError):m.json_safe(value,module.pd)

if __name__=='__main__':unittest.main()
