"""Small synthetic seal chains; no IO, actual seal or production generator."""
import copy,importlib.util,unittest
from pathlib import Path
from backtest import ndx_observation_seal_events_research as m
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('observation_fixture',ROOT/'tests/test_ndx_prospective_observation_parent_history_research.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
def fixture():
 o=f.observation(f.genesis());p=o['payload'];r=o['receipt']
 p.update(conservative_close_utc='2026-10-02T20:00:00+00:00',capture_started_at_utc='2026-10-02T20:01:00+00:00',capture_completed_at_utc='2026-10-02T20:01:01+00:00',writer_started_at_utc='2026-10-02T20:02:00+00:00',writer_completed_at_utc='2026-10-02T20:02:01+00:00',conservative_deadline_utc='2026-10-05T13:30:00+00:00',tzif_reference=f.ref('tzif'))
 r.update(publication_check_at_utc='2026-10-02T20:02:02+00:00',publication_time_role='AFTER_PAYLOAD_FSYNC_AND_SOURCE_GUARD_BEFORE_RECEIPT_WRITE')
 for obj in (p,r,o['audit']):
  obj['source_hashes']['tzif']=p['tzif_reference']['sha256'];ref=p['observation_identity']['parent_reference'];obj['source_hashes'][ref['path']]=ref['sha256']
 inv=dict(schema=m.INVENTORY,observation_id=p['observation_id'],payload_reference=o['payload_reference'],events=[],event_count=0,last_event_sha256=None,inventory_scope=m.SCOPE)
 request=dict(event_type='SEAL_STARTED',recorded_at_utc='2026-10-02T20:03:01+00:00',attempt_started_at_utc='2026-10-02T20:03:00+00:00',candidate_calendar_reference=f.ref('calendar'),input_versions={'model':'future-fixed-version'},input_references={'inputs':f.ref('inputs')})
 return o,inv,request

def proof(o,start):
 refs={k:f.ref(k)for k in ('manifest_reference','audit_reference','reader_reference')};e=start['inventory']['events'][0];identity=e['attempt_identity'];ss={r['path']:r['sha256']for r in [identity['candidate_calendar_reference'],*identity['input_references'].values()]}
 manifest=dict(schema='OBSERVATION_CANDIDATE_SEAL_MANIFEST_V1',status='RESEARCH_SEAL_COMPLETED',observation_id=o['payload']['observation_id'],attempt_id=e['attempt_id'],attempt_started_at_utc=e['attempt_started_at_utc'],attempt_completed_at_utc='2026-10-02T20:04:00+00:00',candidate_calendar_reference=identity['candidate_calendar_reference'],input_versions=identity['input_versions'],input_references=identity['input_references'],source_hashes=ss,extra_original_evidence={'kept':'unchanged'},**m.FLAGS)
 audit=dict(schema='OBSERVATION_CANDIDATE_SEAL_INDEPENDENT_READBACK_V1',status='PASS',manifest_reference=refs['manifest_reference'],reader_sha256=refs['reader_reference']['sha256'],observation_id=manifest['observation_id'],attempt_id=e['attempt_id'],source_hashes={**ss,**{r['path']:r['sha256']for r in refs.values()}},**m.FLAGS)
 return dict(refs,manifest=manifest,audit=audit)
def terminal(start,kind='FAILED'):
 return dict(event_type=kind,recorded_at_utc='2026-10-02T20:04:01+00:00',attempt_completed_at_utc='2026-10-02T20:04:00+00:00',attempt_id=start['attempt_id'],error=dict(error_type='ValueError',message='original failure',stage='validation',traceback=None,original_details={'preserved':True}))
class Tests(unittest.TestCase):
 def test_started_unknown_success_and_original_inputs_unchanged(self):
  o,i,q=fixture();before=copy.deepcopy((o,i,q));start=m.append_seal_event(observation=o,inventory=i,event_request=q)
  self.assertEqual(start['state'],'UNKNOWN_UNRESOLVED');self.assertFalse(start['terminal_event_present']);self.assertEqual((o,i,q),before);self.assertTrue(start['conditional_start_eligible']);self.assertTrue(all(start[k]is False for k in m.FLAGS))
  req=terminal(start,'SEALED');del req['error'];req['success_evidence']=proof(o,start);out=m.append_seal_event(observation=o,inventory=start['inventory'],event_request=req)
  self.assertEqual(out['state'],'SEALED_RESEARCH_EVIDENCE_ONLY');self.assertEqual(out['event_count'],2);self.assertEqual(out['first_actual_observed_session_of_month'],'2026-10-02');self.assertEqual(out['inventory']['events'][1]['success_evidence'],req['success_evidence']);self.assertEqual(out['inventory']['events'][1]['previous_event_sha256'],start['inventory']['last_event_sha256'])
  self.assertNotIn('payload',out);self.assertTrue(all(out[k]is False for k in m.FLAGS))
 def test_late_started_retained_and_late_failure_not_retry(self):
  o,i,q=fixture();q['attempt_started_at_utc']='2026-10-06T20:00:00+00:00';q['recorded_at_utc']='2026-10-06T20:00:01+00:00';start=m.append_seal_event(observation=o,inventory=i,event_request=q)
  self.assertEqual(start['state'],'UNKNOWN_UNRESOLVED');self.assertFalse(start['conditional_start_eligible']);self.assertTrue(start['month_first_actual_observation'])
  req=terminal(start);req.update(attempt_completed_at_utc='2026-10-06T21:00:00+00:00',recorded_at_utc='2026-10-06T21:00:01+00:00');out=m.append_seal_event(observation=o,inventory=start['inventory'],event_request=req);self.assertEqual(out['state'],'FAILED');self.assertEqual(out['inventory']['events'][-1]['error'],req['error'])
  with self.assertRaises(ValueError):m.append_seal_event(observation=o,inventory=out['inventory'],event_request=q)
  with self.assertRaises(ValueError):m.append_seal_event(observation=o,inventory=start['inventory'],event_request=q)
 def test_chain_count_duplicate_and_missing_inventory(self):
  o,i,q=fixture();start=m.append_seal_event(observation=o,inventory=i,event_request=q)
  for mode in ('none','bool','last','hash','sequence','duplicate'):
   bad=copy.deepcopy(start['inventory'])
   if mode=='none':bad=None
   elif mode=='bool':bad['event_count']=True
   elif mode=='last':bad['last_event_sha256']='0'*64
   elif mode=='hash':bad['events'][0]['recorded_at_utc']='2026-10-02T20:05:00+00:00'
   elif mode=='sequence':bad['events'][0]['sequence']=True
   else:bad['events'].append(copy.deepcopy(bad['events'][0]));bad['event_count']=2
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.derive_seal_state(observation=o,inventory=bad)
 def test_success_cannot_accept_just_pass_or_wrong_clock(self):
  o,i,q=fixture();start=m.append_seal_event(observation=o,inventory=i,event_request=q)
  for mode in ('late','schema','source','permission','wrongattempt','missingend'):
   req=terminal(start,'SEALED');del req['error'];req['success_evidence']=proof(o,start);ev=req['success_evidence']
   if mode=='late':req['recorded_at_utc']='2026-10-05T13:30:00+00:00'
   elif mode=='schema':ev['audit']['schema']='ANY_PASS'
   elif mode=='source':ev['audit']['source_hashes']={}
   elif mode=='permission':ev['manifest']['candidate_seal_allowed']=0
   elif mode=='wrongattempt':req['attempt_id']='b'*64
   else:del req['attempt_completed_at_utc']
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.append_seal_event(observation=o,inventory=start['inventory'],event_request=req)
 def test_observation_refs_counts_tzif_and_source_conflicts(self):
  o,i,q=fixture()
  for mode in ('count','reader','tzif','receipt','conflict','naive','inventdeadline'):
   a,b,c=copy.deepcopy((o,i,q))
   if mode=='count':a['audit']['counts']['new_observation_count']=True
   elif mode=='reader':a['audit']['reader_sha256']='f'*64
   elif mode=='tzif':del a['audit']['source_hashes']['tzif']
   elif mode=='receipt':a['receipt']['payload_reference']=f.ref('other')
   elif mode=='conflict':c['input_references']['inputs']=dict(a['payload_reference'],sha256='e'*64)
   elif mode=='naive':c['recorded_at_utc']='2026-10-02T20:05:00'
   else:c['conservative_deadline_utc']='2099-01-01T00:00:00+00:00'
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.append_seal_event(observation=a,inventory=b,event_request=c)
 def test_failure_requires_evidence_not_inferred_from_missing_end(self):
  o,i,q=fixture();start=m.append_seal_event(observation=o,inventory=i,event_request=q)
  for mode in ('missing','empty','end','backward'):
   req=terminal(start)
   if mode=='missing':req['error']={'message':'lost'}
   elif mode=='empty':req['error']['message']=' '
   elif mode=='end':del req['attempt_completed_at_utc']
   else:req['attempt_completed_at_utc']='2026-10-02T20:02:00+00:00'
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.append_seal_event(observation=o,inventory=start['inventory'],event_request=req)
  self.assertEqual(m.derive_seal_state(observation=o,inventory=start['inventory'])['state'],'UNKNOWN_UNRESOLVED')
if __name__=='__main__':unittest.main()
