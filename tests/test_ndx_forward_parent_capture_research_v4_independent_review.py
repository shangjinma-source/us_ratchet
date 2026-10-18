"""Independent V3/V4 capture attacks. No actual capture, publisher or output."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_forward_parent_capture_research_v4 as core
from scripts import ndx_prospective_observation_writer_v3_20261009 as writer
from test_ndx_forward_parent_capture_research_v4 import arguments,resign
from test_ndx_prospective_observation_parent_history_research_v4 import fixture
from test_ndx_prospective_observation_gap_parent_payload_20261009_v3 import arguments as payload_arguments


def v3_arguments(new_dates=()):
    a=fixture();parent=a['parent'];p=a['observation']['payload'];_,data,_=payload_arguments()
    accounted={t:base64.b64decode(p['full_original_sources_preserved'][t]['baseline_sources']['original_csv_bytes_base64'])for t in ('QQQ','SPY')}
    current={t:b+b''.join((d+',10,12,8,10,100\n').encode()for d in new_dates)for t,b in accounted.items()}
    return dict(parent=parent,source_bytes=current,source_references={t:dict(path='v3-current/'+t,sha256=core.sha256(b).hexdigest())for t,b in current.items()},
        accounted_baseline_bytes=accounted,actual_baseline_bytes=data['actual_baseline_bytes'],
        capture_started_at='2026-10-09T20:00:00+00:00',capture_completed_at='2026-10-09T20:00:01+00:00',
        tzif_bytes=base64.b64decode(p['tzif_bytes_base64']),tzif_reference=p['tzif_reference'])


class CaptureV4IndependentTests(unittest.TestCase):
    def test_synthetic_v3_no_new_and_late_candidate_keep_separate_baselines(self):
        a=v3_arguments();before=deepcopy(a);plan=core.plan_parent_capture(**a)
        self.assertEqual(a,before);self.assertEqual(plan['status'],'NO_NEW_SESSION')
        self.assertEqual((len(plan['known_typed_rows']),len(plan['observations'])),(69,1))
        self.assertNotEqual(plan['baseline_references'],plan['accounted_baseline_references'])
        plan=core.plan_parent_capture(**v3_arguments(['2026-10-08']))
        self.assertEqual(plan['candidate_session'],'2026-10-08');self.assertFalse(plan['timeliness_verified'])
        self.assertEqual(plan['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')

    def test_true_saved_v3_readonly_no_new(self):
        parent=deepcopy(writer.PARENT_BOUND)
        for key,role in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:
            parent[key]=json.loads(Path(parent[role]['path']).read_bytes())
        h=parent['document']['history'];old={t:Path(h['captured_source_references'][t]['path']).read_bytes()for t in ('QQQ','SPY')}
        a=dict(parent=parent,source_bytes=deepcopy(old),source_references=deepcopy(h['captured_source_references']),
            accounted_baseline_bytes=old,actual_baseline_bytes={t:Path(h['baseline_references'][t]['path']).read_bytes()for t in ('QQQ','SPY')},
            capture_started_at='2026-10-09T00:00:00+00:00',capture_completed_at='2026-10-09T00:00:01+00:00',
            tzif_bytes=Path(h['tzif_reference']['path']).read_bytes(),tzif_reference=h['tzif_reference'])
        p=core.plan_parent_capture(**a)
        self.assertEqual(p['status'],'NO_NEW_SESSION');self.assertEqual(len(p['known_typed_rows']),69)
        self.assertEqual(p['last_accounted_session'],'2026-10-07');self.assertEqual(p['last_observed_session'],'2026-10-02')

    def test_v3_pending_unfinished_and_original_actual_attempt_corruption(self):
        changes=[lambda h:h.update(pending_source_sessions=[{'session':'2026-10-08'}]),
                 lambda h:h.update(excluded_not_completed_source_sessions=[{'session':'2026-10-08'}]),
                 lambda h:h['parent_attempt_inventory'].append(deepcopy(h['parent_attempt_inventory'][0])),
                 lambda h:h['observations'][0].update(sequence=67)]
        for change in changes:
            a=v3_arguments();change(a['parent']['document']['history'])
            with self.assertRaises(ValueError):core.plan_parent_capture(**a)

    def test_v4_source_hash_scope_duplicate_missing_and_conflict(self):
        a=arguments();a['source_bytes']['QQQ']+=a['source_bytes']['QQQ'].splitlines(keepends=True)[-1];resign(a,'QQQ')
        with self.assertRaises(ValueError):core.plan_parent_capture(**a)
        a=arguments();lines=a['source_bytes']['QQQ'].splitlines(keepends=True);a['source_bytes']['QQQ']=b''.join(lines[:-2]+lines[-1:]);resign(a,'QQQ')
        self.assertEqual(core.plan_parent_capture(**a)['status'],'BLOCKED_SOURCE_DIAGNOSTICS')
        a=arguments(['2026-10-09']);a['source_references']['QQQ']['path']=a['parent']['reference']['path']
        with self.assertRaisesRegex(ValueError,'Conflicting source path'):core.plan_parent_capture(**a)

    def test_clock_exact_close_timezone_and_strict_false(self):
        a=arguments(['2026-10-09']);a['capture_completed_at']=a['capture_started_at']
        self.assertEqual(core.plan_parent_capture(**a)['status'],'ONE_NEW_SESSION_CAPTURE_CANDIDATE')
        a['capture_completed_at']='2026-10-09T19:59:59+00:00'
        with self.assertRaisesRegex(ValueError,'clock reversal'):core.plan_parent_capture(**a)
        a=arguments();raw=Path('D:/python/Lib/site-packages/tzdata/zoneinfo/UTC').read_bytes();a['tzif_bytes']=raw;a['tzif_reference']=dict(path='utc-zone',sha256=core.sha256(raw).hexdigest())
        with self.assertRaisesRegex(ValueError,'Parent TZif'):core.plan_parent_capture(**a)
        for value in (True,0,None):
            a=arguments();a['parent']['readback']['future_independent_oos']=value
            with self.assertRaises(ValueError):core.plan_parent_capture(**a)

    def test_pure_io_free_preserves_all_rows_attempts_and_no_raw(self):
        a=arguments(['2026-10-09']);before=deepcopy(a)
        with (patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),
              patch.object(Path,'write_bytes',side_effect=AssertionError('IO'))):p=core.plan_parent_capture(**a)
        self.assertEqual(a,before);self.assertEqual(p['known_typed_rows'],a['parent']['document']['history']['known_typed_rows'])
        self.assertEqual(p['parent_attempt_inventory'],a['parent']['document']['history']['parent_attempt_inventory'])
        self.assertEqual(set(p['dependency_sha256']),{'scoped','base','parent_view','compact_helpers'})
        self.assertNotIn('original_csv_bytes_base64',str(p));self.assertTrue(all(p[k]is False for k in core.FLAGS))


if __name__=='__main__':unittest.main()
