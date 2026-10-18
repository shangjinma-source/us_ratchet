"""Independent V5 capture planning attacks; actual parent files are read-only."""
from copy import deepcopy
from pathlib import Path
import json
import unittest
from unittest.mock import patch
from backtest import ndx_forward_parent_capture_research_v5 as core
from backtest import ndx_prospective_history_parent_view_research_v5 as view
from scripts import ndx_prospective_observation_writer_v3_20261009 as oldwriter
import test_ndx_forward_parent_capture_research_v5 as author
from test_ndx_forward_parent_capture_research_v4 import arguments as legacy_arguments


class IndependentCaptureV5Tests(unittest.TestCase):
    def test_real_saved_v3_zero_and_late_candidate_keep_original_actual_month(self):
        parent=deepcopy(oldwriter.PARENT_BOUND)
        for key,role in (('document','reference'),('publication','publication_reference'),('readback','readback_reference')):
            parent[key]=json.loads(Path(parent[role]['path']).read_bytes())
        normalized=view.inspect_parent_history_v5(parent)
        old={t:Path(normalized['accounted_baseline_references'][t]['path']).read_bytes()for t in core.TICKERS}
        actual={t:Path(normalized['baseline_references'][t]['path']).read_bytes()for t in core.TICKERS}
        tzif=normalized['tzif_reference'];tzif_bytes=Path(tzif['path']).read_bytes()
        for added,status in ((b'','NO_NEW_SESSION'),(b'2026-10-08,100,110,90,100,1000\n','ONE_NEW_SESSION_CAPTURE_CANDIDATE')):
            raw={t:old[t]+added for t in core.TICKERS}
            args=dict(parent=parent,source_bytes=raw,source_references={t:dict(path='synthetic/v3/'+t,sha256=core.sha256(raw[t]).hexdigest())for t in core.TICKERS},
                accounted_baseline_bytes=old,actual_baseline_bytes=actual,capture_started_at='2026-10-12T20:03:00+00:00',
                capture_completed_at='2026-10-12T20:03:01+00:00',tzif_bytes=tzif_bytes,tzif_reference=tzif)
            with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure IO')):result=core.plan_parent_capture(**args)
            self.assertEqual(result['status'],status);self.assertEqual(len(result['known_typed_rows']),69)
            self.assertEqual(result['actual_parent_schema'],'PROSPECTIVE_GAP_EXTENSION_HISTORY_V3')
            self.assertEqual(result['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
            self.assertIs(result['late_observation_classification_deferred_to_payload_core'],True)
            self.assertTrue(all(result[k]is False for k in core.FLAGS))

    def test_v5_no_suffix_zero_and_future_one_and_dst_close_boundary(self):
        args=author.arguments(())
        self.assertEqual(core.plan_parent_capture(**args)['status'],'NO_NEW_SESSION')
        for t in core.TICKERS:args['source_bytes'][t]+=b'2026-10-12,10,12,8,10,100\n';author.repin(args,t)
        self.assertEqual(core.plan_parent_capture(**args)['candidate_session'],'2026-10-12')
        for clock,candidate in (('2026-11-02T20:59:59+00:00',None),('2026-11-02T21:00:00+00:00','2026-11-02')):
            args=legacy_arguments(('2026-11-02',));args['capture_started_at']=args['capture_completed_at']=clock
            result=core.plan_parent_capture(**args)
            self.assertEqual(result['candidate_session'],candidate)
            if candidate:self.assertEqual(result['candidate_conservative_close_utc'],'2026-11-02T21:00:00+00:00')
            else:self.assertIn('SOURCE_SESSION_NOT_COMPLETED_AT_CAPTURE_START',[x['reason']for x in result['diagnostics']])

    def test_withdrawn_redated_asymmetric_or_multiple_suffix_never_yields_candidate(self):
        for mode in ('redated','asymmetric','multiple'):
            a=author.arguments(('2026-10-12','2026-10-13')if mode=='multiple'else('2026-10-12',))
            if mode=='redated':
                for t in core.TICKERS:a['source_bytes'][t]=a['source_bytes'][t].replace(b'2026-10-12,',b'2026-10-13,');author.repin(a,t)
            elif mode=='asymmetric':a['source_bytes']['SPY']+=b'2026-10-13,10,12,8,10,100\n';author.repin(a,'SPY')
            before=deepcopy(a);result=core.plan_parent_capture(**a)
            self.assertEqual(a,before);self.assertEqual(result['status'],'BLOCKED_SOURCE_DIAGNOSTICS');self.assertIsNone(result['candidate_session'])
            self.assertEqual(result['known_typed_rows'],a['parent']['document']['history']['known_typed_rows'])

    def test_swapped_baseline_roles_and_revised_accounted_bytes_cannot_be_observed(self):
        a=author.arguments();a['accounted_baseline_bytes']=deepcopy(a['actual_baseline_bytes'])
        with self.assertRaises(ValueError):core.plan_parent_capture(**a)
        a=author.arguments();a['actual_baseline_bytes']=deepcopy(a['accounted_baseline_bytes'])
        with self.assertRaises(ValueError):core.plan_parent_capture(**a)
        a=author.arguments()
        for t in core.TICKERS:a['source_bytes'][t]=a['source_bytes'][t].replace(b'2026-10-09,10,12,8,10,100',b'2026-10-09,10,12,8,11,100');author.repin(a,t)
        result=core.plan_parent_capture(**a)
        self.assertIsNone(result['candidate_session']);self.assertIn('ACCOUNTED_BASELINE_PREFIX_REVISED',[x['reason']for x in result['diagnostics']])

    def test_clock_tzif_hash_and_parent_authority_fail_closed_without_io(self):
        for mode in ('clock','nonutc','tzif','sourcehash','authority'):
            a=author.arguments()
            if mode=='clock':a['capture_completed_at']='2026-10-12T20:01:00+00:00'
            elif mode=='nonutc':a['capture_started_at']='2026-10-12T20:03:00+08:00'
            elif mode=='tzif':a['tzif_bytes']+=b'changed'
            elif mode=='sourcehash':a['source_references']['QQQ']['sha256']='f'*64
            else:a['parent']['publication']['future_independent_oos']=True
            with self.subTest(mode=mode),patch.object(Path,'read_bytes',side_effect=AssertionError('Pure IO')),self.assertRaises(ValueError):core.plan_parent_capture(**a)

    def test_detached_complete_suffix_provenance_and_source_claims(self):
        a=author.arguments(('2026-10-12','2026-10-13'));before=deepcopy(a)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure IO')):result=core.plan_parent_capture(**a)
        self.assertEqual(a,before);self.assertEqual(result['parent_full_capture_source_references'],a['parent']['document']['history']['full_capture_source_references'])
        for t in core.TICKERS:self.assertEqual(result['source_reference_claims'][a['source_references'][t]['path']],a['source_references'][t]['sha256'])
        result['parent_pending_source_sessions'][0]['session']='2099-01-01';self.assertEqual(a,before)
        self.assertEqual(result['dependency_sha256']['parent_view'],core.PARENT_VIEW_SHA256)
        self.assertEqual(result['dependency_sha256']['legacy_view'],core.LEGACY_VIEW_SHA256)


if __name__=='__main__':unittest.main()
