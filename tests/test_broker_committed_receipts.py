"""Post-save auxiliary failures must not report an unsuccessful broker mutation."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from contextlib import ExitStack
from api.server import api_update_broker_position,api_sync_broker_snapshot
from core.broker_account import save_broker_account,load_broker_account,broker_account_fingerprint

class BrokerCommitReceiptTests(unittest.TestCase):
    def exercise(self,kind,failed):
        with TemporaryDirectory() as folder,ExitStack() as stack:
            path=Path(folder)/'broker.json'
            save_broker_account(dict(snapshot_as_of='2026-10-15',positions=[dict(ticker='AAA',shares=2,average_cost=10,observed_price=10)],deployable_cash_usd=0),path)
            original=path.read_bytes();fingerprint=broker_account_fingerprint(load_broker_account(path))
            stack.enter_context(patch('api.server.BROKER_ACCOUNT_PATH',path))
            stack.enter_context(patch('api.server.audit_log',side_effect=OSError('audit') if failed=='audit' else None))
            stack.enter_context(patch('api.server.load_portfolio',side_effect=OSError('load') if failed=='load' else None,return_value=object()))
            stack.enter_context(patch('api.server._state_payload',side_effect=RuntimeError('projection') if failed=='projection' else None,return_value={'initialized':True}))
            if failed=='save':stack.enter_context(patch('api.server.save_broker_account',side_effect=OSError('save')))
            fn=api_update_broker_position if kind=='position' else api_sync_broker_snapshot
            body=dict(ticker='AAA',shares=1,account_fingerprint=fingerprint) if kind=='position' else dict(mode='snapshot',text='ticker,shares,avg_price\nAAA,1,10',expected_account_fingerprint=fingerprint)
            if failed=='save':
                with self.assertRaises(OSError):fn(body)
                self.assertEqual(path.read_bytes(),original);return
            result=fn(body)
            self.assertEqual(load_broker_account(path)['positions'][0]['shares'],1)
            self.assertTrue(result['committed']);self.assertEqual(result['account_fingerprint'],broker_account_fingerprint(load_broker_account(path)))
            expected='BROKER_AUDIT_FAILED' if failed=='audit' else 'BROKER_STATE_REFRESH_FAILED'
            self.assertIn(expected,[w['code'] for w in result['warnings']]);self.assertEqual(path.with_suffix('.json.bak').read_bytes(),original)
            self.assertEqual(fn(body).status_code,409)
    def test_position_audit_after_commit(self):self.exercise('position','audit')
    def test_snapshot_auxiliary_failures_after_commit(self):
        for failure in ('audit','load','projection'):
            with self.subTest(failure=failure):self.exercise('snapshot',failure)
    def test_actual_save_failure_is_not_committed(self):
        for kind in ('position','snapshot'):
            with self.subTest(kind=kind):self.exercise(kind,'save')

if __name__=='__main__':unittest.main()
