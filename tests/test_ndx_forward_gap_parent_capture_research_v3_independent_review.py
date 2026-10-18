"""Synthetic adversarial review; never starts capture or observation IO."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_forward_gap_parent_capture_research_v3 as module
from test_ndx_forward_gap_parent_capture_research_v3 import fixture, resign


def history(arguments):
    return arguments['parent']['document']['history']


class IndependentReviewTests(unittest.TestCase):
    def test_actual_attempt_identity_and_unique_inventory_required(self):
        for mode in ('payload', 'receipt', 'audit', 'coordinated_payload', 'duplicate', 'unresolved_extra'):
            a = fixture(); h = history(a); attempt = h['parent_attempt_inventory'][0]
            if mode in ('payload', 'receipt', 'audit'):
                key = {'payload':'payload_reference', 'receipt':'receipt_reference',
                       'audit':'independent_readback_reference'}[mode]
                attempt[key] = deepcopy(h['observations'][0]['reader_reference'])
            elif mode == 'coordinated_payload':
                changed=deepcopy(h['observations'][0]['reader_reference'])
                attempt['payload_reference']=changed
                h['observations'][0]['payload_reference']=deepcopy(changed)
            elif mode == 'duplicate':
                h['parent_attempt_inventory'].append(deepcopy(attempt))
            else:
                extra = deepcopy(attempt); extra.update(session='2026-10-06', status='STARTED')
                h['parent_attempt_inventory'].append(extra)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                module.plan_gap_parent_capture(**a)

    def test_outer_inner_parent_and_capture_associations_required(self):
        for key in ('parent_history_reference', 'parent_publication_reference',
                    'parent_readback_reference', 'capture_reference',
                    'capture_publication_reference', 'capture_readback_reference'):
            a = fixture()
            history(a)[key] = deepcopy(a['parent']['reader_reference'])
            # This reference is already bound in the envelope; add to wrapper source maps
            # so the attack tests identity coupling rather than an omitted source claim.
            ref = history(a)[key]
            for role in ('document', 'publication', 'readback'):
                a['parent'][role]['source_hashes'][ref['path']] = ref['sha256']
            with self.subTest(key=key), self.assertRaises(ValueError):
                module.plan_gap_parent_capture(**a)

    def test_bytes_prefix_cannot_be_replaced_by_equivalent_normalized_rows(self):
        a = fixture()
        raw = a['source_bytes']['QQQ'].replace(b'\n', b'\r\n')
        a['source_bytes']['QQQ'] = raw; resign(a, 'QQQ')
        plan = module.plan_gap_parent_capture(**a)
        self.assertEqual(plan['status'], 'BLOCKED_SOURCE_DIAGNOSTICS')
        self.assertIn({'reason':'ACCOUNTED_BASELINE_PREFIX_REVISED','ticker':'QQQ'}, plan['diagnostics'])

    def test_baseline_scope_hash_tzif_and_source_map_lies_rejected(self):
        for mode in ('old_hash','actual_hash','tzif','map','old_scope'):
            a = fixture()
            if mode == 'old_hash': a['accounted_baseline_bytes']['QQQ'] += b'changed'
            elif mode == 'actual_hash': a['actual_baseline_bytes']['SPY'] += b'changed'
            elif mode == 'tzif': a['tzif_bytes'] += b'changed'
            elif mode == 'map': a['source_bytes']['DIA'] = b''
            else:
                raw = a['accounted_baseline_bytes']['QQQ'] + b'2026-10-08,10,12,8,10,100\n'
                a['accounted_baseline_bytes']['QQQ'] = raw
                history(a)['captured_source_references']['QQQ']['sha256'] = sha256(raw).hexdigest()
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                module.plan_gap_parent_capture(**a)

    def test_pending_suffixes_and_strict_authority_flags(self):
        for role in ('document','publication','readback'):
            for value in (True, 0, None):
                a = fixture(); a['parent'][role]['future_independent_oos'] = value
                with self.subTest(role=role,value=value), self.assertRaises(ValueError):
                    module.plan_gap_parent_capture(**a)
        for key in ('pending_source_sessions','excluded_not_completed_source_sessions'):
            for value in (None,{},[{'session':'2026-10-08'}]):
                a = fixture(); history(a)[key] = value
                with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                    module.plan_gap_parent_capture(**a)

    def test_candidate_at_close_and_late_do_not_create_or_authorize_observation(self):
        for clock in ('2026-10-08T20:00:00+00:00','2026-10-12T21:00:00+00:00'):
            a = fixture(['2026-10-08'],clock); before=deepcopy(a)
            with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure IO')):
                plan=module.plan_gap_parent_capture(**a)
            self.assertEqual(a,before)
            self.assertEqual(plan['candidate_session'],'2026-10-08')
            self.assertTrue(all(plan[k] is False for k in module.FLAGS))
            self.assertEqual(plan['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')

    def test_prefix_deletion_and_different_single_new_dates_block(self):
        a=fixture(['2026-10-08']); a['source_bytes']['QQQ']=b'\n'.join(a['source_bytes']['QQQ'].split(b'\n')[:-2])+b'\n'; resign(a,'QQQ')
        self.assertEqual(module.plan_gap_parent_capture(**a)['status'],'BLOCKED_SOURCE_DIAGNOSTICS')
        a=fixture(['2026-10-08']); a['source_bytes']['SPY']=a['source_bytes']['SPY'].replace(b'2026-10-08',b'2026-10-09'); resign(a,'SPY')
        self.assertIn({'reason':'ASYMMETRIC_NEW_SESSION_DATES'},module.plan_gap_parent_capture(**a)['diagnostics'])

    def test_reference_conflicts_reader_status_and_clock_strictness(self):
        for mode in ('status','readerrole','conflict','naive','reverse'):
            a=fixture()
            if mode=='status': a['parent']['readback']['status']='PASS'
            elif mode=='readerrole': a['parent']['readback']['publisher_called']=0
            elif mode=='conflict':
                ref=a['parent']['reference']; a['parent']['readback']['source_hashes'][ref['path']]='f'*64
            elif mode=='naive': a['capture_started_at']='2026-10-09T21:00:00'
            else: a['capture_completed_at']='2026-10-09T20:00:00+00:00'
            with self.subTest(mode=mode),self.assertRaises(ValueError):module.plan_gap_parent_capture(**a)

    def test_different_valid_tzif_cannot_replace_parent_timezone_binding(self):
        a=fixture(['2026-10-08'],'2026-10-08T20:00:00+00:00')
        raw=Path('D:/python/Lib/site-packages/tzdata/zoneinfo/UTC').read_bytes()
        a['tzif_bytes']=raw
        a['tzif_reference']={'path':'alternate-utc-tzif','sha256':sha256(raw).hexdigest()}
        with self.assertRaises(ValueError):module.plan_gap_parent_capture(**a)

    def test_known_optional_parent_authority_cannot_contradict_mandatory_flags(self):
        for role in ('document','publication','readback'):
            for key in set(module.FLAGS)-set(module.WRAPPER_FALSE):
                a=fixture(); a['parent'][role][key]=True
                with self.subTest(role=role,key=key),self.assertRaises(ValueError):
                    module.plan_gap_parent_capture(**a)


if __name__=='__main__':unittest.main()
