"""Independent declaration attacks; no source authenticity is inferred."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_prospective_history_parent_view_research_v5 as view
from backtest import ndx_prospective_gap_history_research_v5 as gap
import test_ndx_prospective_history_parent_view_research_v5 as author


class IndependentParentViewV5Tests(unittest.TestCase):
    def test_self_consistent_suffix_reclassification_cannot_use_regressed_clock(self):
        args,h=author.fixture();first=author.wrap(h)
        second=gap.extend_gap_history(**author.next_arguments(first,args,(),(),'2026-10-12T20:03:00+00:00','clock-second'))
        second['capture_started_at']=second['capture_completed_at']='2026-10-12T19:00:00+00:00'
        second['excluded_not_completed_source_sessions']=second['pending_source_sessions']+second['excluded_not_completed_source_sessions']
        second['pending_source_sessions']=[]
        for item in second['excluded_not_completed_source_sessions']:
            item['capture_started_at_utc']=item['capture_completed_at_utc']=second['capture_started_at']
            item['classification']='SOURCE_ROW_NOT_COMPLETED_AT_CAPTURE_START'
        with self.assertRaises(ValueError):view.inspect_parent_history_v5(author.wrap(second,'regressed-clock'))

    def test_every_known_authority_role_rejects_true_and_numeric_false(self):
        _,h=author.fixture()
        for role in ('document','publication','readback','history','counts'):
            for bad in (True,0):
                parent=author.wrap(h)
                target=parent['document']['history']if role=='history'else parent['readback']['counts']if role=='counts'else parent[role]
                target['source_authenticity_verified']=bad
                with self.subTest(role=role,bad=bad),self.assertRaises(ValueError):view.inspect_parent_history_v5(parent)

    def test_prior_flat_snapshot_requires_suffix_roles_and_cannot_rewrite_baselines_or_attempts(self):
        args,h=author.fixture();first=author.wrap(h)
        second=gap.extend_gap_history(**author.next_arguments(first,args,('2026-10-14',),('2026-10-12',),
            '2026-10-13T20:02:00+00:00','independent-second'))
        for mode in ('missing','legacy_role','prior_consumed','prior_false_zero','actual_baseline','attempt_reference','recursive'):
            forged=deepcopy(second);prior=forged['prior_state_preserved']
            if mode=='missing':del prior['full_capture_source_references']
            elif mode=='legacy_role':prior['full_capture_source_role']='LEGACY_COMPLETE_ACCOUNTED_SNAPSHOT_NO_SUFFIX_DECLARED'
            elif mode=='prior_consumed':prior['pending_source_sessions'][0]['counts_as_observed_session']=True
            elif mode=='prior_false_zero':prior['excluded_not_completed_source_sessions'][0]['decision_eligible']=0
            elif mode=='actual_baseline':forged['baseline_references']=deepcopy(forged['accounted_prefix_references'])
            elif mode=='attempt_reference':forged['parent_attempt_inventory'][0]['payload_reference']['sha256']='f'*64
            else:prior['prior_state_preserved']={}
            with self.subTest(mode=mode),self.assertRaises(ValueError):view.inspect_parent_history_v5(author.wrap(forged,'forgery'))

    def test_source_closure_readback_pointers_and_prefix_artifact_roles_are_checked(self):
        _,h=author.fixture()
        for mode in ('wrapper_missing','audit_missing','reader_pointer','artifact_conflict','prefix_as_full','schema','status'):
            parent=author.wrap(h);full=parent['document']['history']['full_capture_source_references']['QQQ']
            if mode=='wrapper_missing':
                for role in ('document','publication'):parent[role]['source_hashes'].pop(full['path'])
            elif mode=='audit_missing':parent['readback']['source_hashes'].pop(full['path'])
            elif mode=='reader_pointer':parent['readback']['reader_sha256']='f'*64
            elif mode=='artifact_conflict':parent['document']['history']['accounted_prefix_evidence_references']['QQQ']['sha256']='f'*64
            elif mode=='prefix_as_full':parent['document']['history']['accounted_prefix_evidence']['QQQ']['full_source_reference']=deepcopy(h['accounted_prefix_references']['QQQ'])
            elif mode=='schema':parent['document']['schema']='SOURCE_BOUND_PROSPECTIVE_GAP_HISTORY_V3'
            else:parent['readback']['status']='PASS'
            with self.subTest(mode=mode),self.assertRaises(ValueError):view.inspect_parent_history_v5(parent)

    def test_pure_detached_view_keeps_full_suffix_and_absolute_legacy_role_without_authentication(self):
        _,h=author.fixture();parent=author.wrap(h);before=deepcopy(parent)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure view IO')):
            normalized=view.inspect_parent_history_v5(parent)
        self.assertEqual(parent,before);self.assertTrue(Path(normalized['legacy_checker_reference']['path']).is_absolute())
        self.assertFalse(normalized['legacy_checker_called']);self.assertTrue(all(normalized[k]is False for k in view.FLAGS))
        state=view.parent_state_for_gap(normalized)
        self.assertEqual(set(state),set(view.STATE_KEYS));self.assertNotIn('prior_state_preserved',state)
        self.assertEqual(state['baseline_references'],h['baseline_references'])
        self.assertEqual(state['accounted_baseline_references'],h['accounted_prefix_references'])
        self.assertEqual(state['full_capture_source_references'],h['full_capture_source_references'])
        state['pending_source_sessions'][0]['session']='2099-01-01'
        self.assertEqual(normalized['pending_source_sessions'][0]['session'],'2026-10-12')


if __name__=='__main__':unittest.main()
