import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_historical_single_window_accounts_20260920 import state
from test_ndx_fixed_control_accounting_independent_audit_research import fixture
from scripts import ndx_historical_single_window_accounts_20260920 as m


class WrapperReview(unittest.TestCase):
    def test_marker_changed_or_deleted_after_engine_keeps_raw_and_never_retries(self):
        for defect in ('change', 'delete'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                def execute(**kwargs):
                    marker = base/'candidate/started.json'
                    if defect == 'delete': marker.unlink()
                    else: marker.write_text('{}')
                    return {'unmodified_raw': [1, 2, 3]}
                with patch.object(m, 'BASE', base), patch.object(m, 'prepare', return_value=state('candidate')), patch.object(m, 'verify_sources', return_value={}), patch.object(m.candidate, 'simulate_dynamic_frozen_execution_research', side_effect=execute) as engine:
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        m.run(track='candidate', execute=True)
                    saved = json.loads((base/'candidate/raw_execution.json').read_bytes())
                    self.assertEqual(saved['execution'], {'unmodified_raw': [1, 2, 3]})
                    self.assertFalse((base/'candidate/account.json').exists())
                    self.assertTrue((base/'candidate/failure.json').exists())
                    with self.assertRaises(FileExistsError): m.run(track='candidate', execute=True)
                    self.assertEqual(engine.call_count, 1)

    def test_restoration_changes_only_ticker_labels_and_audits_control_zero_slots(self):
        args = fixture()
        original = args['execution']
        targets = args['schedule'][0]['targets']
        columns = {sid: 'SID_'+sid for sid in targets}
        raw = copy.deepcopy(original)
        for row in raw['decisions']:
            for sid, value in row['targets'].items(): value['ticker'] = columns[sid]
        for row in raw['trades']: row['ticker'] = columns[row['security_id']]
        for row in raw['daily']: row['tickers'] = {sid: columns[sid] for sid in row['shares']}
        prepared = dict(track='incumbent', calendar=args['calendar'], contract=args['contract'], effective_schedule=args['schedule'], selected=dict(columns=columns, labels=targets, prices=args['prices'], arguments=dict(risk_chains_by_decision=args['risk_chains_by_decision'])))
        prior = copy.deepcopy(raw)
        restored, audit = m.restore_and_audit(raw, prepared)
        self.assertEqual(raw, prior)
        self.assertEqual(restored, original)
        self.assertEqual(audit['zero_share_security_ids'], ['s7'])
        raw['daily'][2]['cash_usd'] += 1
        with self.assertRaises(ValueError): m.restore_and_audit(raw, prepared)

    def test_candidate_one_normalization_control_original_weights(self):
        weights = [.25+1e-13, .25, .25, .25]
        schedule = [dict(decision_date='2026-03-18', execution_date='2026-03-19', targets={str(i): dict(ticker='T'+str(i), issuer_id='I'+str(i), target_weight=w) for i,w in enumerate(weights)})]
        track = dict(original_schedule=schedule)
        assembly = dict(candidate=track, incumbent=track, calendar=[], contract={})
        inputs = dict(historical_expected_source_hashes={})
        target = dict(inputs, schedule=schedule, risk_chains_by_decision={})
        audit = dict(inputs, target_reference=m.TARGET, input_reference=m.INPUT)
        with patch.object(m, 'AUDIT_SHA', 'a'*64), patch.object(m.target_reader, 'read', side_effect=[inputs,target,audit]*2), patch.object(m.target_reader,'verify'), patch.object(m.assembly,'assemble_account_arguments',return_value=assembly), patch.object(m,'verify_sources',return_value={}):
            candidate = m.prepare('candidate')
            control = m.prepare('incumbent')
        self.assertNotEqual(candidate['effective_schedule'], schedule)
        self.assertEqual(candidate['selected']['original_schedule'], schedule)
        self.assertEqual(control['effective_schedule'], schedule)
        self.assertEqual(control['normalization_evidence']['normalization_count'], 0)


if __name__ == '__main__': unittest.main()
