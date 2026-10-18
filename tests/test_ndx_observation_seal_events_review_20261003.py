"""Independent state-machine attacks, wholly synthetic and without dispatch."""
import copy,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from backtest import ndx_observation_seal_events_research as m
import test_ndx_observation_seal_events_research as f
import test_ndx_prospective_observation_independent_readback_v2_20261003 as v2

def start(o,i,q):return m.append_seal_event(observation=o,inventory=i,event_request=q)
def successful(o,s):
    req=f.terminal(s,'SEALED');req.pop('error');req['success_evidence']=f.proof(o,s);return req
def resign(inv):
    previous=None
    for e in inv['events']:
        e['previous_event_sha256']=previous;e['event_sha256']=m.digest({k:v for k,v in e.items()if k!='event_sha256'});previous=e['event_sha256']
    inv['last_event_sha256']=previous
def observed_v2():
    a=v2.fixture(True,True);p,r=a['payload'],a['receipt'];refs=dict(payload_reference=a['payload_reference'],receipt_reference=f.f.ref('v2receipt'),audit_reference=f.f.ref('v2audit'),reader_reference=f.f.ref('v2reader'))
    sources=copy.deepcopy(p['source_hashes'])
    for value in refs.values():sources[value['path']]=value['sha256']
    audit=dict(schema='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V2',status='PASS',payload_reference=refs['payload_reference'],receipt_reference=refs['receipt_reference'],reader_sha256=refs['reader_reference']['sha256'],parent_history_reference=p['observation_identity']['parent_reference'],source_hashes=sources,counts=v2.m.inspect(**a),**dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','point_in_time_verified','promotion_allowed'),False))
    return dict(refs,payload=p,receipt=r,audit=audit)

class Review(unittest.TestCase):
    def test_resigned_semantic_attacks_cannot_become_success(self):
        o,i,q=f.fixture();s=start(o,i,q);ok=m.append_seal_event(observation=o,inventory=s['inventory'],event_request=successful(o,s))
        for mode in ('late','manifestclock','calendar','boolpermission','eventcount','attempt'):
            inv=copy.deepcopy(ok['inventory']);e=inv['events'][-1];proof=e['success_evidence']
            if mode=='late':e['recorded_at_utc']=o['payload']['conservative_deadline_utc']
            elif mode=='manifestclock':proof['manifest']['attempt_completed_at_utc']='2026-10-02T20:03:30+00:00'
            elif mode=='calendar':proof['manifest']['candidate_calendar_reference']=f.f.ref('other-calendar')
            elif mode=='boolpermission':proof['audit']['candidate_seal_allowed']=0
            elif mode=='eventcount':inv['event_count']=2.0
            else:e['attempt_id']='e'*64
            resign(inv)
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.derive_seal_state(observation=o,inventory=inv)
        self.assertEqual(m.derive_seal_state(observation=o,inventory=s['inventory'])['state'],'UNKNOWN_UNRESOLVED')
    def test_late_nonfirst_start_and_failure_preserve_observation(self):
        o=observed_v2();_,i,q=f.fixture();i.update(observation_id=o['payload']['observation_id'],payload_reference=o['payload_reference']);q.update(attempt_started_at_utc='2026-10-09T15:01:00+00:00',recorded_at_utc='2026-10-09T15:01:01+00:00');before=copy.deepcopy((o,i,q))
        s=start(o,i,q);self.assertFalse(s['conditional_start_eligible']);self.assertIn('NOT_FIRST_ACTUAL_OBSERVATION_OF_MONTH',s['start_ineligibility_reasons']);self.assertIn('OBSERVATION_RECEIPT_LATE',s['start_ineligibility_reasons'])
        req=f.terminal(s);req.update(attempt_completed_at_utc='2026-10-09T15:02:00+00:00',recorded_at_utc='2026-10-09T15:02:01+00:00');out=m.append_seal_event(observation=o,inventory=s['inventory'],event_request=req)
        self.assertEqual(out['state'],'FAILED');self.assertEqual(out['first_actual_observed_session_of_month'],'2026-10-02');self.assertTrue(all(out[k]is False for k in m.FLAGS));self.assertEqual((o,i,q),before)
        with self.assertRaises(ValueError):m.append_seal_event(observation=o,inventory=out['inventory'],event_request=q)
        out['inventory']['events'][0]['attempt_identity']['input_versions']['model']='mutated';self.assertEqual(s['inventory']['events'][0]['attempt_identity']['input_versions']['model'],'future-fixed-version')
    def test_v2_explicit_parent_link_and_full_source_conflicts(self):
        o=observed_v2();m.observed(o)
        for mode in ('parent','reader','conflict','tzif','floatcount'):
            b=copy.deepcopy(o)
            if mode=='parent':b['audit']['parent_history_reference']=f.f.ref('wrong-parent')
            elif mode=='reader':b['audit']['reader_sha256']='0'*64
            elif mode=='conflict':b['receipt']['source_hashes'][b['payload']['tzif_reference']['path']]='f'*64
            elif mode=='tzif':b['audit']['source_hashes'].pop(b['payload']['tzif_reference']['path'])
            else:b['audit']['counts']['new_observation_count']=1.0
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.observed(b)
if __name__=='__main__':unittest.main()
