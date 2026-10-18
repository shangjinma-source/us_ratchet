"""Independent first-V1 calendar attacks; synthetic inputs, no writer/generator."""
import copy,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from backtest import ndx_first_persisted_candidate_calendar_research as m
import test_ndx_first_persisted_candidate_calendar_research as f

def extra_source(a):
    path='additional-original-code';value='9'*64;h=a['history']['document'];o=a['observation'];entry=h['observations'][0]
    for obj in (o['payload'],o['receipt'],o['audit'],h,a['history']['publication'],a['history']['readback']):obj['source_hashes'][path]=value
    h['source_reference_claims'][path]=value
    for role in ('payload','receipt','audit'):entry['original_source_hash_claims'][role][path]=value
    return path

class Review(unittest.TestCase):
    def test_synchronized_compact_cannot_hide_missing_observation_sources(self):
        for role in ('receipt','audit'):
            a=f.fixture();key=extra_source(a);m.prepare_first_persisted_candidate_evidence(**a)
            a['observation'][role]['source_hashes'].pop(key);a['history']['document']['observations'][0]['original_source_hash_claims'][role].pop(key)
            with self.subTest(role=role),self.assertRaises(ValueError):m.prepare_first_persisted_candidate_evidence(**a)
    def test_first_actual_is_never_replaced_by_success_or_late_receipt(self):
        for state in ('FAILED','UNKNOWN','SEALED'):
            a=f.fixture();a['history']['document']['known_typed_rows'][-1]['seal_status']=state;before=copy.deepcopy(a);out=m.prepare_first_persisted_candidate_evidence(**a)
            self.assertEqual(out['status'],'BLOCKED');self.assertTrue(out['monthly_coordinate']);self.assertEqual(out['first_actual_observed_session_by_month']['2026-10'],'2026-10-02');self.assertEqual(a,before)
            self.assertTrue(all(out[k]is False for k in m.FALSE))
        a=f.fixture();a['observation']['receipt'].update(publication_check_at_utc='2026-10-05T13:30:00+00:00',timing_classification='LATE_OBSERVATION');a['observation']['audit']['counts']['timing_classification']='LATE_OBSERVATION';a['history']['document']['observations'][0]['timing_classification']='LATE_OBSERVATION';a['seal_evaluation_at_utc']='2026-10-05T13:30:01+00:00'
        out=m.prepare_first_persisted_candidate_evidence(**a);self.assertEqual(out['status'],'BLOCKED');self.assertTrue(out['monthly_coordinate'])
    def test_versions_typed_prefix_original_clock_and_permission(self):
        for mode in ('v2audit','foreignreceipt','genesis','floatcount','clock','permission','pointer'):
            a=f.fixture()
            if mode=='v2audit':a['observation']['audit']['schema']='PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V2'
            elif mode=='foreignreceipt':a['observation']['receipt']['writer_adapter_schema']='FOREIGN'
            elif mode=='genesis':a['genesis']['readback']['schema']='GAP_MONTHLY_POLICY_HISTORY_INPUT_READBACK_V2'
            elif mode=='floatcount':a['capture']['readback']['accounted_prefix_count']=65.0
            elif mode=='clock':
                a['capture']['document']['capture_started_at_utc']='2026-10-02T19:59:00+00:00';a['capture']['readback']['capture_started_at_utc']='2026-10-02T19:59:00+00:00';a['observation']['payload']['capture_started_at_utc']='2026-10-02T19:59:00+00:00'
            elif mode=='permission':a['genesis']['readback']['candidate_seal_allowed']=0
            else:a['observation']['payload']['source_row_locations']['QQQ']['original_data_row_index']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.prepare_first_persisted_candidate_evidence(**a)
if __name__=='__main__':unittest.main()
