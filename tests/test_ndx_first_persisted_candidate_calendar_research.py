from copy import deepcopy
import unittest
from backtest import ndx_first_persisted_candidate_calendar_research as m
from backtest import ndx_prospective_observation_parent_history_research as history_core
from test_ndx_prospective_observation_independent_readback_20261003 import fixture as original
from test_ndx_prospective_observation_parent_history_research import envelope,ref


def fixture():
 p,r,started,docs,refs,pr,blobs,session=original()
 flags=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed','live_mutation_allowed'),False)
 g=docs['parent'];g.update(source_hashes={},**flags)
 genesis=envelope(g,'genesis',True)
 # Preserve original V1 identity parent references from the original fixture.
 genesis['reference']=refs['parent'];genesis['publication_reference']=refs['parent_publication'];genesis['readback_reference']=refs['parent_readback']
 genesis['publication']['policy_reference']=refs['parent']
 ga=genesis['readback'];ga.update(policy_reference=refs['parent'],publication_reference=refs['parent_publication'],known_typed_rows_preserved=deepcopy(g['projection_inputs']['known_rows']),counts=dict(known_rows=65,observed_rows=60,gap_rows=5,new_observation_count=0))
 c=docs['capture'];refs['capture']['path']='C:/research/capture/capture.json';refs['capture_publication']['path']='C:/research/capture/publication.json'
 p['observation_identity']['capture_reference']=deepcopy(refs['capture']);p['observation_id']=m.digest(p['observation_identity']);r['observation_id']=p['observation_id']
 for t in ('QQQ','SPY'):
  snapshot=c['captured_artifacts'][t];snapshot['path']='C:/research/capture/'+t+'.csv';p['full_original_sources_preserved'][t]['sources']['reference']=deepcopy(snapshot);p['source_row_locations'][t]['reference']=deepcopy(snapshot);c['input_references']['current_'+t]=dict(path='C:/research/data/cache/'+t+'.csv',sha256=snapshot['sha256'])
 base={t:c['input_references']['baseline_'+t]for t in ('QQQ','SPY')};genesis['baseline_references']=base;ga['baseline_references']=deepcopy(base)
 ga['source_hashes']={x['path']:x['sha256']for x in [genesis[k]for k in m.ENVELOPE_REFS]+list(base.values())}
 c.update(schema='FORWARD_SOURCE_CAPTURE_SCOPED_PAYLOAD_V1',source_hashes={x['path']:x['sha256']for x in list(c['captured_artifacts'].values())+list(base.values())},**flags)
 c['source_hashes'].update({c['input_references']['current_'+t]['path']:c['input_references']['current_'+t]['sha256']for t in ('QQQ','SPY')})
 c['plan'].update(schema='FORWARD_SOURCE_CAPTURE_SCOPED_PLAN_V1',**flags)
 c['plan']['capture_plan'].update(status='NEW_SOURCE_DATES_REQUIRE_REVIEW',schema='FORWARD_SOURCE_CAPTURE_PLANNING_V1',excluded_unfinished_source_dates=[],unmatched_new_source_dates_by_ticker=dict(QQQ=[],SPY=[]),source_suffix_asymmetry_blocks_timeliness_candidate=False)
 classification=dict(session=session,classification='TIMELINESS_REVIEW_CANDIDATE_ONLY',capture_started_at_utc=c['capture_started_at_utc'],observed_at_utc=c['observed_at_utc'],conservative_close_utc=p['conservative_close_utc'],conservative_next_weekday_open_utc=p['conservative_deadline_utc'])
 c['plan']['capture_plan'].update(classifications=[classification],timeliness_candidate=deepcopy(classification))
 cap=dict(reference=refs['capture'],publication_reference=refs['capture_publication'],readback_reference=ref('capture_audit'),reader_reference=ref('capture_reader'),document=c)
 cap['publication']=dict(schema='FORWARD_SOURCE_CAPTURE_SCOPED_PUBLICATION_V1',status='PUBLISHED_CURRENT_CACHE_CAPTURE_NOT_CALENDAR_APPEND',capture_reference=cap['reference'],source_hashes=deepcopy(c['source_hashes']),**flags)
 cap['readback']=dict(schema='SCOPED_FORWARD_CAPTURE_INDEPENDENT_READBACK_V1',status='PASS',capture_reference=cap['reference'],publication_reference=cap['publication_reference'],reader_sha256=cap['reader_reference']['sha256'],capture_original_source_hashes_preserved=deepcopy(c['source_hashes']),source_hashes={**{k:v for k,v in c['source_hashes'].items()if not m.is_live_cache(k)},**{cap[k]['path']:cap[k]['sha256']for k in m.ENVELOPE_REFS}},status_observed='NEW_SOURCE_DATES_REQUIRE_REVIEW',candidate=deepcopy(classification),current_live_cache_reopened=False,producer_called=False,old_audit_called=False,new_source_dates=[session],revision_count=0,accounted_prefix_count=65,capture_started_at_utc=c['capture_started_at_utc'],observed_at_utc=c['observed_at_utc'],**flags)
 claims={**{k:v for k,v in c['source_hashes'].items()if not m.is_live_cache(k)},**{v['path']:v['sha256']for v in refs.values()}}
 p['source_hashes']=deepcopy(claims);r['source_hashes']=deepcopy(claims)
 o=dict(payload=p,receipt=r,payload_reference=pr,receipt_reference=ref('receipt'),audit_reference=ref('observation_audit'),reader_reference=ref('observation_reader'))
 o['audit']=dict(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V1',status='PASS',payload_reference=pr,receipt_reference=o['receipt_reference'],reader_sha256=o['reader_reference']['sha256'],source_hashes={**claims,**{o[k]['path']:o[k]['sha256']for k in m.OBS_REFS}},writer_called=False,old_audit_repeated=False,counts=dict(parent_observed_count=60,parent_gap_count=5,new_observation_count=1,month_first_actual_observation=True,timing_classification=p['timing_classification']),**flags)
 h=history_core.append_observation_history(genesis=genesis,previous_history=None,observation=o)
 hist=envelope(h,'history');hist['readback']['counts']=dict(typed_row_count=66,observation_count=1,new_observation_count=1,first_actual_observed_session_by_month=deepcopy(h['first_actual_observed_session_by_month']))
 return dict(history=hist,genesis=genesis,observation=o,capture=cap,tzif_bytes=blobs[c['captured_artifacts']['tzif']['path']],seal_evaluation_at_utc='2026-10-02T20:00:05+00:00')


class Tests(unittest.TestCase):
 def test_snapshot_bridge_is_exact_two_capture_roles_only(self):
  a=fixture();out=m.prepare_first_persisted_candidate_evidence(**a)
  self.assertEqual(len(out['snapshot_equivalence_bridge']['rows']),2)
  self.assertFalse(any(m.is_live_cache(p)for p in out['source_hash_claims']))
  self.assertEqual(out['original_source_claims_preserved'],a['capture']['document']['source_hashes'])
  for mode in ('third','snapshot_path','hash','original_map','audit_snapshot','parent_live','no_bridge'):
   a=fixture();c=a['capture']['document'];audit=a['capture']['readback'];pub=a['capture']['publication']
   if mode=='third':
    for d in (c['source_hashes'],pub['source_hashes'],audit['capture_original_source_hashes_preserved']):d['C:/research/data/cache/DIA.csv']='a'*64
   elif mode=='snapshot_path':c['captured_artifacts']['QQQ']['path']='C:/elsewhere/QQQ.csv'
   elif mode=='hash':c['input_references']['current_QQQ']['sha256']='a'*64
   elif mode=='original_map':audit['capture_original_source_hashes_preserved']={}
   elif mode=='audit_snapshot':del audit['source_hashes'][c['captured_artifacts']['QQQ']['path']]
   elif mode=='parent_live':
    h=a['history'];live=c['input_references']['current_QQQ']
    for d in (h['document']['source_hashes'],h['publication']['source_hashes'],h['readback']['source_hashes']):d[live['path']]=live['sha256']
   else:del c['input_references']['current_QQQ']
   with self.subTest(mode=mode),self.assertRaises((ValueError,KeyError)):m.prepare_first_persisted_candidate_evidence(**a)
 def test_timely_first_actual_and_immutable_authority(self):
  a=fixture();before=deepcopy(a);out=m.prepare_first_persisted_candidate_evidence(**a)
  self.assertEqual(a,before);self.assertTrue(out['monthly_coordinate']);self.assertTrue(out['calendar_prerequisites_conditionally_satisfied']);self.assertEqual(len(out['known_typed_rows_preserved']),66)
  self.assertTrue(all(out[k]is False for k in m.FALSE))
 def test_late_seal_failed_unknown_never_replace_month(self):
  a=fixture();a['seal_evaluation_at_utc']='2026-10-05T13:30:00+00:00';out=m.prepare_first_persisted_candidate_evidence(**a)
  self.assertEqual(out['status'],'BLOCKED');self.assertTrue(out['monthly_coordinate'])
  for state in ('FAILED','UNKNOWN'):
   a=fixture();a['history']['document']['known_typed_rows'][-1]['seal_status']=state
   out=m.prepare_first_persisted_candidate_evidence(**a);self.assertEqual(out['status'],'BLOCKED');self.assertEqual(out['original_seal_status'],state);self.assertTrue(out['monthly_coordinate'])
 def test_versions_prefix_sources_and_compact_fields_fail_closed(self):
  changes=[lambda a:a['observation']['payload'].update(writer_adapter_schema='VARIABLE_PREFIX_OBSERVATION_WRITER_V2'),lambda a:a['observation']['receipt'].update(writer_adapter_schema='VARIABLE_PREFIX_OBSERVATION_WRITER_V2'),lambda a:a['observation']['audit'].update(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V2'),lambda a:a['history']['document']['known_typed_rows'][0].update(seal_status='SEALED'),lambda a:a['history']['document']['observations'][0].update(month_first_actual_observation=False),lambda a:a['capture']['readback'].update(source_hashes={}),lambda a:a['observation']['payload']['input_references'].update(parent=ref('wrong')),lambda a:a['history']['document'].update(source_hashes={})]
  for change in changes:
   with self.subTest(change=change):
    a=fixture();change(a)
    with self.assertRaises((ValueError,KeyError)):m.prepare_first_persisted_candidate_evidence(**a)
 def test_compact_cannot_hide_missing_receipt_or_audit_source(self):
  for role in ('receipt','audit'):
   a=fixture();extra=ref('original_writer_code')
   for name in ('payload','receipt','audit'):
    a['observation'][name]['source_hashes'][extra['path']]=extra['sha256']
   h=a['history']['document']
   for name in ('source_hashes','source_reference_claims'):h[name][extra['path']]=extra['sha256']
   for name in ('publication','readback'):a['history'][name]['source_hashes'][extra['path']]=extra['sha256']
   entry=h['observations'][0]
   for name in ('payload','receipt','audit'):entry['original_source_hash_claims'][name]=deepcopy(a['observation'][name]['source_hashes'])
   m.prepare_first_persisted_candidate_evidence(**a)
   del a['observation'][role]['source_hashes'][extra['path']]
   entry['original_source_hash_claims'][role]=deepcopy(a['observation'][role]['source_hashes'])
   with self.subTest(role=role),self.assertRaises(ValueError):m.prepare_first_persisted_candidate_evidence(**a)
 def test_late_receipt_preserved_not_promoted(self):
  a=fixture();r=a['observation']['receipt'];r.update(publication_check_at_utc='2026-10-05T13:30:00+00:00',timing_classification='LATE_OBSERVATION')
  a['observation']['audit']['counts']['timing_classification']='LATE_OBSERVATION'
  a['history']['document']['observations'][0]['timing_classification']='LATE_OBSERVATION'
  a['seal_evaluation_at_utc']='2026-10-05T13:30:01+00:00'
  out=m.prepare_first_persisted_candidate_evidence(**a);self.assertEqual(out['status'],'BLOCKED');self.assertIn('PERSISTED_OBSERVATION_PUBLICATION_CHECK_LATE',out['reasons']);self.assertTrue(out['monthly_coordinate'])

if __name__=='__main__':unittest.main()
