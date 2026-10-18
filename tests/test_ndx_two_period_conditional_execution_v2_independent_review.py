"""Independent interruption/tampering cases; mocked engine only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_two_period_conditional_execution_v2_20260919 as m
from test_ndx_two_period_conditional_execution_v2_20260919 import prepared_fixture


class ExecutionReview(unittest.TestCase):
    def test_marker_tampering_after_engine_preserves_raw_but_rejects_account(self):
        prepared,normalized,evidence,raw = prepared_fixture()
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);output=base/'two_period_conditional_execution_20260919_v2/account.json'
            def engine(**kwargs):
                Path(str(output)+'.started.json').write_text('{}')
                return raw
            with patch.object(m,'BASE',base),patch.object(m,'prepare',return_value=(prepared,normalized,evidence,{},[])), \
                 patch.object(m.prior,'verify_gaps'),patch.object(m.prior.archive,'load_contract'), \
                 patch.object(m.prior.archive,'verify_expected_sources',return_value={}), \
                 patch.object(m.prior.engine,'simulate_dynamic_frozen_execution_research',side_effect=engine) as call, \
                 patch.object(m,'restore_and_audit') as audit:
                with self.assertRaises(ValueError):m.run(output=output,execute=True)
                self.assertFalse(output.exists())
                self.assertTrue(Path(str(output)+'.raw_execution.json').exists())
                self.assertEqual(audit.call_count,0)
                with self.assertRaises(FileExistsError):m.run(output=output,execute=True)
                self.assertEqual(call.call_count,1)

    def test_raw_tampering_during_audit_rejects_account(self):
        prepared,normalized,evidence,raw=prepared_fixture()
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);output=base/'two_period_conditional_execution_20260919_v2/account.json'
            def audit(*args):
                Path(str(output)+'.raw_execution.json').write_text('{}')
                return raw,{}
            with patch.object(m,'BASE',base),patch.object(m,'prepare',return_value=(prepared,normalized,evidence,{},[])), \
                 patch.object(m.prior,'verify_gaps'),patch.object(m.prior.archive,'load_contract'), \
                 patch.object(m.prior.archive,'verify_expected_sources',return_value={}), \
                 patch.object(m.prior.engine,'simulate_dynamic_frozen_execution_research',return_value=raw), \
                 patch.object(m,'restore_and_audit',side_effect=audit):
                with self.assertRaises(ValueError):m.run(output=output,execute=True)
                self.assertFalse(output.exists())
                failure=json.loads(Path(str(output)+'.failure.json').read_bytes())
                self.assertFalse(failure['automatic_retry_allowed'])


if __name__=='__main__':unittest.main()
