import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.ndx_offline_saved_fund_signal_diagnostic_20260923 import build_report, read_saved_row


class SavedDiagnosticTests(unittest.TestCase):
    def fixture(self):
        snapshot={'snapshot_id':'saved-1','execution':{'items':[dict(ticker='MSFT',side='BUY',
            source='tactical_limit',action='PLACE_LIMIT',share_plan_eligible=True,amount=118,limit=498.43)]},
            'execution_constraints':dict(lot_size=1,allow_fractional=False,fee_bps=10,min_fee=1)}
        return json.dumps(snapshot).encode(),snapshot

    def test_pinned_row_and_id_mismatch(self):
        raw,snapshot=self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'journal.jsonl';path.write_bytes(raw+b'\r\n'+b'{"snapshot_id":"later"}\n')
            digest=hashlib.sha256(raw).hexdigest()
            self.assertEqual(read_saved_row(path,'saved-1',digest)[0],raw)
            with self.assertRaisesRegex(ValueError,'snapshot_id mismatch'):
                read_saved_row(path,'other',digest)
            with self.assertRaisesRegex(ValueError,'not present'):
                read_saved_row(path,'saved-1','0'*64)

    def test_missing_gap_and_fees_are_not_zero_defaults(self):
        raw,snapshot=self.fixture();del snapshot['execution_constraints']['fee_bps']
        report=build_report(json.dumps(snapshot).encode(),'10000');row=report['rows'][0]
        self.assertIn('account.position_gaps.rows',report['missing_snapshot_fields'])
        self.assertIn('GAP_ROW_MISSING',row['unknown_codes'])
        self.assertIn('RESEARCH_CASH_OR_FEE_UNKNOWN',row['unknown_codes'])
        self.assertIn('STRATEGY_BUDGET_BELOW_ONE_UNIT',row['blocking_codes'])
        self.assertEqual(row['action'],'PLACE_LIMIT')
        self.assertFalse(report['research_cash_is_user_current_cash'])
        self.assertFalse(report['order_authorized'])

    def test_missing_execution_rejected_and_valid_gap_preserved(self):
        raw,snapshot=self.fixture()
        snapshot['account']={'position_gaps':{'rows':[dict(ticker='MSFT',gap_amount=0,position_kind='real_position')]}}
        report=build_report(json.dumps(snapshot).encode(),'1000')
        self.assertIn('NO_POSITIVE_REAL_GAP',report['rows'][0]['blocking_codes'])
        self.assertEqual(report['missing_snapshot_fields'],[])
        del snapshot['execution']
        with self.assertRaisesRegex(ValueError,'execution.items'):
            build_report(json.dumps(snapshot).encode(),'1000')


if __name__=='__main__':
    unittest.main()
