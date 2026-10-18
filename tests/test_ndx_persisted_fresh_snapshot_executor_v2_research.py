"""Small synthetic full-NDX computation and variable-gap calendar boundaries only."""
from copy import deepcopy
from hashlib import sha256
import unittest
from unittest.mock import patch
from backtest import ndx_persisted_fresh_snapshot_executor_research as old
from backtest import ndx_persisted_fresh_snapshot_executor_v2_research as m
from test_ndx_persisted_fresh_snapshot_executor_research import fixture as prior_fixture,ref


def fixture(later=False):
 a=prior_fixture('later'if later else'first');x=a['execution_input'];r=a['registration'];x['schema']=m.INPUT_SCHEMA
 r.update(schema='OBSERVATION_CANDIDATE_EXECUTOR_REGISTRATION_V2',entry_point=m.ENTRY,executor_reference=dict(path=str(m.SOURCE),sha256=m.LOADED_SHA),input_schema=m.INPUT_SCHEMA,output_schema=m.OUTPUT_SCHEMA)
 c=x['calendar'];e=c['document']['evidence']
 if not later:
  for obj,key in [(c['document'],'schema'),(c['publication'],'schema'),(c['readback'],'schema'),(e,'schema')]:obj[key]=obj[key][:-2]+'V2'
 months={}
 for row in e['known_typed_rows_preserved']:
  if row['kind']!='MISSED_OBSERVATION':months.setdefault(row['session'][:7],row['session'])
 e['first_actual_observed_session_by_month']=months
 return a


def validate(a,module=m):
 x=a['execution_input'];return module.calendar_evidence(x['calendar'],x['observation_references'],x['observation_id'],module.utc(a['execution_started_at_utc']),{})

class Tests(unittest.TestCase):
 def test_new_exact_registration_and_first_v2_old_red(self):
  a=fixture()
  with self.assertRaises(ValueError):validate(a,old)
  self.assertEqual(m.validate_registration(a['registration'])['entry_point'],m.ENTRY)
  b=deepcopy(a['registration']);b['entry_point']=old.ENTRY
  with self.assertRaises(ValueError):m.validate_registration(b)
  self.assertEqual(len(validate(a)['known_typed_rows_preserved']),66)
  a['execution_input']['calendar']['readback']['schema']='FIRST_PERSISTED_CANDIDATE_CALENDAR_SNAPSHOT_INDEPENDENT_READBACK_V1'
  with self.assertRaisesRegex(ValueError,'version'):validate(a)
 def test_later_sixth_gap_preserved_and_original_prefix_fixed(self):
  a=fixture(True);e=a['execution_input']['calendar']['document']['evidence'];rows=e['known_typed_rows_preserved'];rows.insert(66,dict(sequence=67,session='2026-10-30',kind='MISSED_OBSERVATION',seal_status='NOT_ATTEMPTED',evidence_reference=dict(ref('new-gap-evidence'),json_pointer='/rows/0')));rows[-1]['sequence']=68;e['selected_existing_row']=deepcopy(rows[-1]);before=deepcopy(a)
  self.assertEqual(sum(r['kind']=='MISSED_OBSERVATION'for r in validate(a)['known_typed_rows_preserved']),6);self.assertEqual(a,before)
  with self.assertRaisesRegex(ValueError,'five gaps'):validate(a,old)
  for attack in ('missing_evidence','bad_pointer','sealed_gap','prefix'):
   b=deepcopy(a);rr=b['execution_input']['calendar']['document']['evidence']['known_typed_rows_preserved']
   if attack=='missing_evidence':rr[66]['evidence_reference']={'path':'relative','sha256':'a'*64}
   elif attack=='bad_pointer':rr[66]['evidence_reference']['json_pointer']='/bad~2escape'
   elif attack=='sealed_gap':rr[66]['seal_status']='SEALED'
   else:rr[60]['kind']='SEALED_PARENT_OBSERVED_SESSION'
   with self.subTest(attack=attack),self.assertRaises(ValueError):validate(b)
 def test_failed_or_unknown_actual_observation_still_owns_month(self):
  for state in ('FAILED','UNKNOWN'):
   a=fixture(True);e=a['execution_input']['calendar']['document']['evidence'];rows=e['known_typed_rows_preserved'];first=deepcopy(rows[-1]);first['seal_status']=state;rows[-1]=first;rows.append(dict(sequence=68,session='2026-11-03',kind='PROSPECTIVE_OBSERVED_SESSION',seal_status='NOT_ATTEMPTED'));e['selected_existing_row']=deepcopy(rows[-1])
   with self.subTest(state=state),self.assertRaisesRegex(ValueError,'earlier actual'):validate(a)
 def test_full_ndx_synthetic_small_snapshot_no_seal_or_old_generator(self):
  a=fixture();before=deepcopy(a)
  with patch.object(old,'execute_fresh_input_snapshot',side_effect=AssertionError('No old executor')):out=m.execute_fresh_input_snapshot(**a)
  self.assertEqual(a,before);self.assertEqual(out['schema'],m.OUTPUT_SCHEMA);self.assertFalse(out['industry_filter_applied']);self.assertEqual([r['theoretical_security_combinations']for r in out['snapshot']['job_plan']['rows']],[4,5,2]);self.assertTrue(all(out[k]is False for k in m.FLAGS));self.assertEqual(out['calendar_evidence_preserved']['lineage_blockers'],before['execution_input']['calendar']['document']['evidence']['lineage_blockers'])

if __name__=='__main__':unittest.main()
