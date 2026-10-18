import copy,hashlib,unittest
from datetime import datetime,timedelta
from backtest import ndx_persisted_candidate_calendar_research as m
from test_ndx_prospective_observation_independent_readback_v2_20261003 import fixture as upstream

def reference(name):return dict(path=name,sha256=hashlib.sha256(name.encode()).hexdigest())
def replace(v,old,new):
 if type(v)is dict:return {k:replace(x,old,new)for k,x in v.items()}
 if type(v)is list:return [replace(x,old,new)for x in v]
 if type(v)is str:return v.replace(old,new)
 return v

def fixture(newmonth=True):
 a=upstream();p=copy.deepcopy(a['payload']);receipt=copy.deepcopy(a['receipt']);cap=copy.deepcopy(a['docs']['capture']);parent=copy.deepcopy(a['docs']['parent'])
 if newmonth:
  p=replace(p,'2026-10-05','2026-11-02');receipt=replace(receipt,'2026-10-05','2026-11-02');cap=replace(cap,'2026-10-05','2026-11-02')
  p['conservative_close_utc']='2026-11-02T21:00:00+00:00';p['conservative_deadline_utc']='2026-11-03T14:30:00+00:00';p['month_first_actual_observation']=True;p['first_actual_observed_session_of_month']=p['session'];receipt['month_first_actual_observation']=True
 p['observation_id']=m.digest(p['observation_identity']);receipt['observation_id']=p['observation_id'];orefs={k:reference('new-'+k)for k in m.OBS_REFS};receipt['payload_reference']=orefs['payload_reference']
 aud=dict(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V2',status='PASS',payload_reference=orefs['payload_reference'],receipt_reference=orefs['receipt_reference'],reader_sha256=orefs['reader_reference']['sha256'],parent_history_reference=parent['reference'],input_references=p['input_references'],counts=dict(parent_observed_count=61,parent_gap_count=5,new_observation_count=1,month_first_actual_observation=p['month_first_actual_observation'],timing_classification=receipt['timing_classification']),source_hashes=dict(p['source_hashes']),writer_called=False,old_audit_repeated=False,**dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'),False))
 for k in ('payload_reference','receipt_reference','reader_reference'):aud['source_hashes'][orefs[k]['path']]=orefs[k]['sha256']
 obs=dict(orefs,payload=p,receipt=receipt,audit=aud);h=copy.deepcopy(parent['document']);entry={k:copy.deepcopy(p[k])for k in ('observation_id','observation_identity','session','sequence','initial_seal_status','month_first_actual_observation','first_actual_observed_session_of_month')};entry.update(schema='COMPACT_OBSERVATION_REFERENCE_ENTRY_V1',original_payload_embedded=False,timing_classification=receipt['timing_classification'],payload_timing_classification=p['timing_classification'],captured_baseline_references={t:cap['document']['captured_artifacts'][t]for t in ('QQQ','SPY')},previous_baseline_references=copy.deepcopy(cap['document']['plan']['baseline_references']),original_source_hash_claims={k:copy.deepcopy(o['source_hashes'])for k,o in [('payload',p),('receipt',receipt),('audit',aud)]},**orefs)
 h['observations'].append(entry);h['known_typed_rows'].append(dict(sequence=p['sequence'],session=p['session'],kind=p['kind'],seal_status='NOT_ATTEMPTED',evidence_reference=dict(orefs['payload_reference'],json_pointer='/observation_identity')));h['parent_attempt_inventory'].append(dict(observation_id=p['observation_id'],session=p['session'],status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',payload_reference=orefs['payload_reference'],receipt_reference=orefs['receipt_reference'],independent_readback_reference=orefs['audit_reference']));h.update(observation_count=2,last_accounted_session=p['session'],baseline_references=entry['captured_baseline_references']);h['first_actual_observed_session_by_month'].setdefault(p['session'][:7],p['session'])
 for value in orefs.values():h['source_hashes'][value['path']]=value['sha256']
 for obj in (p,receipt,aud):h['source_hashes'].update(obj['source_hashes'])
 hrefs={k:reference('final-history-'+k)for k in m.ENVELOPE_REFS};pub=dict(schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_PUBLICATION_V2',status='PUBLISHED_OBSERVATION_HISTORY_NO_SEAL',history_reference=hrefs['reference'],source_hashes=h['source_hashes'],**dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'),False));ha=dict(schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_INDEPENDENT_READBACK_V2',status='PASS',history_reference=hrefs['reference'],publication_reference=hrefs['publication_reference'],reader_sha256=hrefs['reader_reference']['sha256'],source_hashes=dict(h['source_hashes']),counts=dict(typed_row_count=67,observation_count=2,new_observation_count=1,first_actual_observed_session_by_month=h['first_actual_observed_session_by_month']),**dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'),False))
 for k in ('reference','publication_reference','reader_reference'):ha['source_hashes'][hrefs[k]['path']]=hrefs[k]['sha256']
 history=dict(hrefs,document=h,publication=pub,readback=ha);tz=a['blobs'][p['tzif_reference']['path']]
 return dict(history=history,observation=obs,capture=cap,tzif_bytes=tz,seal_evaluation_at_utc=p['session']+'T21:02:00+00:00')

class Tests(unittest.TestCase):
 def test_existing_id_not_reappended_full_prefix_immutable_new_month(self):
  a=fixture();before=copy.deepcopy(a);out=m.prepare_persisted_candidate_evidence(**a);self.assertEqual(a,before);self.assertTrue(out['calendar_prerequisites_conditionally_satisfied']);self.assertEqual(len(out['known_typed_rows_preserved']),67);self.assertEqual(out['first_actual_observed_session_by_month']['2026-10'],'2026-10-02');self.assertTrue(all(out[k]is False for k in m.FALSE));self.assertIn('SEAL_STATUS_EVENT_HISTORY_NOT_BOUND',out['lineage_blockers'])
 def test_prior_failed_unknown_and_capture_timely_seal_late(self):
  for state in ('FAILED','UNKNOWN'):
   a=fixture(False);h=a['history']['document'];h['known_typed_rows'][65]['seal_status']=state;a['observation']['payload']['known_typed_rows_preserved'][65]['seal_status']=state;a['capture']['document']['plan']['known_typed_rows_preserved'][65]['seal_status']=state
   out=m.prepare_persisted_candidate_evidence(**a);self.assertFalse(out['monthly_coordinate']);self.assertEqual(out['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
  a=fixture();a['seal_evaluation_at_utc']=a['observation']['payload']['conservative_deadline_utc'];out=m.prepare_persisted_candidate_evidence(**a);self.assertIn('SEAL_EVALUATION_OUTSIDE_CONSERVATIVE_WINDOW',out['reasons'])
  a=fixture();a['history']['document']['known_typed_rows'][-1]['seal_status']='FAILED';self.assertIn('PRIOR_SEAL_STATE_DOES_NOT_AUTHORIZE_NEW_ATTEMPT',m.prepare_persisted_candidate_evidence(**a)['reasons'])
 def test_receipt_prefix_id_ref_count_authority_and_tzif_attacks(self):
  for mode in ('prefix','reference','id','count','authority','v1','tzif','capture','inventory'):
   a=fixture()
   if mode=='prefix':a['observation']['payload']['known_typed_rows_preserved'].pop(2)
   elif mode=='reference':a['observation']['payload_reference']=reference('foreign')
   elif mode=='id':a['observation']['payload']['observation_id']='a'*64
   elif mode=='count':a['history']['readback']['counts']['new_observation_count']=True
   elif mode=='authority':a['capture']['readback']['candidate_seal_allowed']=0
   elif mode=='v1':a['observation']['audit']['schema']='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1'
   elif mode=='tzif':a['tzif_bytes']+=b'x'
   elif mode=='capture':a['capture']['document']['plan']['source_evidence']['SPY']['new_session_dates'].append('2026-11-03')
   else:a['history']['document']['parent_attempt_inventory'][0]['status']='STARTED_ONLY'
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.prepare_persisted_candidate_evidence(**a)
 def test_later_observation_no_backfill_and_no_seal_clock(self):
  a=fixture();h=a['history']['document'];e=copy.deepcopy(h['observations'][-1]);e.update(session='2026-11-03',sequence=68,observation_identity=dict(e['observation_identity'],session='2026-11-03'));e['observation_id']=m.digest(e['observation_identity']);e.update({k:reference('later-'+k)for k in m.OBS_REFS});h['observations'].append(e);h['known_typed_rows'].append(dict(sequence=68,session=e['session'],kind='PROSPECTIVE_OBSERVED_SESSION',seal_status='UNKNOWN',evidence_reference=dict(e['payload_reference'],json_pointer='/observation_identity')));h['parent_attempt_inventory'].append(dict(observation_id=e['observation_id'],session=e['session'],status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',payload_reference=e['payload_reference'],receipt_reference=e['receipt_reference'],independent_readback_reference=e['audit_reference']));h.update(observation_count=3,last_accounted_session=e['session']);a['history']['readback']['counts'].update(typed_row_count=68,observation_count=3)
  self.assertIn('LATER_OBSERVED_SESSION_NO_BACKFILL',m.prepare_persisted_candidate_evidence(**a)['reasons'])
  a=fixture();a['seal_evaluation_at_utc']=None;self.assertIn('SEAL_CLOCK_NOT_SUPPLIED',m.prepare_persisted_candidate_evidence(**a)['reasons'])

if __name__=='__main__':unittest.main()
