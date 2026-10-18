"""Synthetic independent recovery review; no actual saved raw readback."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_cprt_single_task_independent_readback_20260925 as owner

m = owner.m


class Review(unittest.TestCase):
    def test_exception_cannot_claim_risk_failure_postcheck(self):
        c = owner.case()
        c['raw'].update(status='FIT_EXCEPTION', fitted=None, returned_fit_count=0,
                        error=dict(type='ValueError', message='finally source failure'))
        detail = m.inspect_envelopes(**c)
        rr = dict(path='raw.json', sha256='b'*64)
        post = dict(schema='NEW_CUTOFF_CPRT_SINGLE_TASK_POSTCHECK_V1',
                    status='ORIGINAL_RISKS_FAILED_PENDING_INDEPENDENT_READBACK',
                    started_reference=c['started_reference'], raw_reference=rr,
                    numerical_task_id=c['state']['task']['numerical_task_id'], checks=None,
                    error=None, **dict.fromkeys(m.FALSE, False))
        with self.assertRaises(ValueError):
            m.validate_postcheck(post, c['started_reference'], rr,
                                 c['state']['task']['numerical_task_id'], detail)
        self.assertEqual(m.summary_status(detail, None), 'NUMERICAL_EXCEPTION_NO_RETURNED_FIT')

    def test_unselected_panel_authority_and_unknown_fullpanel_number(self):
        for attack in ('authority', 'nonfinite', 'oldprior'):
            docs, panel, taskid = owner.authorized_fixture()
            if attack == 'authority':
                panel[m.codec.PANEL_FALSE[0]] = True
            elif attack == 'nonfinite':
                panel['returns'].iloc[-1, -2] = float('nan')
            else:
                docs['queue']['new_materializations'][-1]['combinations'][0]['tasks'][0]['numerical_identity']['requested_previous_target_weights'] = {}
            with self.subTest(attack=attack), patch.object(m.codec, 'decode_frames', return_value=panel):
                with self.assertRaises(ValueError):
                    m.expected_state(docs, taskid)

    def test_orphan_namespace_refuses_before_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            task = 'a'*64
            folder = Path(directory)/task
            folder.mkdir()
            for name in ('started.json', 'raw.json', 'orphan.json'):
                (folder/name).write_text('{}')
            with patch.object(m, 'OUTPUT_ROOT', Path(directory)), patch.object(m, 'guard') as guard:
                with self.assertRaises(ValueError):
                    m.build(task, 'b'*64, 'c'*64)
                guard.assert_not_called()

    def test_loaded_conflict_before_disk(self):
        path, digest = next(iter(m.LOADED.items()))
        with patch.object(m.Path, 'read_bytes', side_effect=AssertionError('no read')):
            with self.assertRaises(ValueError):
                m.guard({path: '0'*64 if digest != '0'*64 else '1'*64})


if __name__ == '__main__':
    unittest.main()
