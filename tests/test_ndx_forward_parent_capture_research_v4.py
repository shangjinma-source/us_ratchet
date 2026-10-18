"""Synthetic future V4 captures; no IO publisher or new actual observations."""
import base64
from copy import deepcopy
from hashlib import sha256
import unittest
from backtest import ndx_forward_parent_capture_research_v4 as module
from backtest import ndx_prospective_observation_parent_history_research_v4 as history
from test_ndx_prospective_observation_parent_history_research_v4 import fixture,wrap


def arguments(new_dates=()):
    initial=fixture();result=history.append_observation_history_v4(**initial)
    parent=wrap(result);parts=initial['observation']['payload']['full_original_sources_preserved']
    baseline={t:base64.b64decode(parts[t]['sources']['original_csv_bytes_base64'])for t in ('QQQ','SPY')}
    current={t:raw+b''.join((date+',10,12,8,10,100\n').encode()for date in new_dates)for t,raw in baseline.items()}
    return dict(parent=parent,source_bytes=current,
        source_references={t:dict(path='next-current/'+t,sha256=sha256(raw).hexdigest())for t,raw in current.items()},
        accounted_baseline_bytes=deepcopy(baseline),actual_baseline_bytes=deepcopy(baseline),
        capture_started_at='2026-10-09T20:00:00+00:00',capture_completed_at='2026-10-09T20:00:01+00:00',
        tzif_bytes=base64.b64decode(initial['observation']['payload']['tzif_bytes_base64']),
        tzif_reference=initial['observation']['payload']['tzif_reference'])


def resign(args,ticker):args['source_references'][ticker]['sha256']=sha256(args['source_bytes'][ticker]).hexdigest()


class ForwardParentCaptureV4Tests(unittest.TestCase):
    def test_after_actual_v4_no_new_preserves_history_and_baseline_roles(self):
        args=arguments();before=deepcopy(args);plan=module.plan_parent_capture(**args)
        self.assertEqual(args,before);self.assertEqual(plan['status'],'NO_NEW_SESSION')
        self.assertEqual(len(plan['known_typed_rows']),70)
        self.assertEqual(len(plan['observations']),2)
        self.assertEqual(sum(row['kind']=='MISSED_OBSERVATION'for row in plan['known_typed_rows']),8)
        self.assertEqual(plan['accounted_baseline_references'],args['parent']['document']['history']['accounted_baseline_references'])
        self.assertEqual(plan['baseline_references'],args['parent']['document']['history']['baseline_references'])
        self.assertTrue(all(plan[key]is False for key in module.FLAGS))

    def test_unique_next_session_is_candidate_only_not_observation(self):
        plan=module.plan_parent_capture(**arguments(['2026-10-09']))
        self.assertEqual(plan['status'],'ONE_NEW_SESSION_CAPTURE_CANDIDATE')
        self.assertEqual(plan['candidate_session'],'2026-10-09')
        self.assertEqual(plan['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
        self.assertFalse(plan['observation_created']);self.assertFalse(plan['future_independent_oos'])
        self.assertEqual(plan['dependency_sha256']['parent_view'],module.PARENT_VIEW_SHA256)

    def test_multi_asymmetric_and_revised_sources_are_diagnostics(self):
        cases=[]
        multi=arguments(['2026-10-09','2026-10-12']);cases.append((multi,'MULTIPLE_UNACCOUNTED_SESSIONS'))
        asymmetric=arguments(['2026-10-09']);asymmetric['source_bytes']['SPY']=asymmetric['accounted_baseline_bytes']['SPY'];resign(asymmetric,'SPY');cases.append((asymmetric,'ASYMMETRIC_NEW_SESSION_DATES'))
        revised=arguments(['2026-10-09']);revised['source_bytes']['QQQ']=revised['source_bytes']['QQQ'].replace(b',10,12,8,10,100',b',10,12,8,11,100',1);resign(revised,'QQQ');cases.append((revised,'ACCOUNTED_BASELINE_PREFIX_REVISED'))
        for args,reason in cases:
            with self.subTest(reason=reason):
                plan=module.plan_parent_capture(**args)
                self.assertEqual(plan['status'],'BLOCKED_SOURCE_DIAGNOSTICS')
                self.assertIsNone(plan['candidate_session'])
                self.assertIn(reason,[item['reason']for item in plan['diagnostics']])

    def test_capture_interval_must_start_after_candidate_close(self):
        args=arguments(['2026-10-09']);args['capture_started_at']='2026-10-09T19:59:59+00:00'
        plan=module.plan_parent_capture(**args)
        self.assertEqual(plan['status'],'BLOCKED_SOURCE_DIAGNOSTICS')
        self.assertIsNone(plan['candidate_session'])
        self.assertIn('SOURCE_SESSION_NOT_COMPLETED_AT_CAPTURE_START',[r['reason']for r in plan['diagnostics']])

    def test_unread_parent_or_unaccounted_bytes_do_not_become_candidate(self):
        args=arguments(['2026-10-09']);args['parent']['readback']['status']='PENDING'
        with self.assertRaises(ValueError):module.plan_parent_capture(**args)
        args=arguments(['2026-10-09']);args['accounted_baseline_bytes']['QQQ']+=b'2026-10-09,10,12,8,10,100\n'
        with self.assertRaises(ValueError):module.plan_parent_capture(**args)


if __name__=='__main__':unittest.main()
