import base64
from copy import deepcopy
from datetime import timedelta
import tempfile
import unittest

import test_current_research_intraday_retarget_sources as sources
from data.current_research_intraday_execution_reference import read_intraday_execution_reference
from data.current_research_intraday_retarget_sizing import build_intraday_retarget_sizing
from data.current_research_intraday_retarget_ledger import apply_retarget_event
from data.current_research_intraday_retarget_evidence import (
    accept_retarget_with_execution_evidence, review_source_verified_retarget)


class FrozenRetargetTests(unittest.TestCase):
    def fixture(self, root):
        state, arguments = sources.RetargetSourcesTests().fixture(root)
        inputs = {key: arguments[key] for key in ('selection', 'selection_inputs', 'execution_unit_continuity', 'source_hashes')}
        inputs['execution_references'] = {sid: read_intraday_execution_reference(root=root,
            now=arguments['now'], **value) for sid, value in arguments['execution_inputs'].items()}
        proposal = build_intraday_retarget_sizing(state, now=arguments['now'], **inputs)
        self.assertEqual(proposal['status'], 'READY', proposal)
        acceptance = dict(root=root, sizing_inputs=inputs, execution_inputs=arguments['execution_inputs'],
            market_session=arguments['selection_inputs']['capital_inputs']['market_session'],
            operation_id='activate-month', now=arguments['now'])
        return state, proposal, acceptance

    def test_source_files_not_needed_for_acceptance_and_fill_replay(self):
        with tempfile.TemporaryDirectory() as root:
            old, proposal, arguments = self.fixture(root)
            envelope = accept_retarget_with_execution_evidence(old, proposal, **arguments)
            accepted = arguments['now']
        self.assertEqual(review_source_verified_retarget(envelope), envelope)
        state = envelope['ledger']
        self.assertEqual(state['cash'], old['cash'])
        self.assertEqual(state['account_id'], old['account_id'])
        self.assertEqual(state['acceptance_id'], old['acceptance_id'])
        sell = next(row for row in state['orders'].values() if row['side'] == 'SELL')
        event = dict(event_id='sell-real-record', kind='FILL', expected_revision=state['revision'],
            order_id=sell['order_id'], recorded_at=(accepted+timedelta(seconds=130)).isoformat(),
            executed_at=(accepted+timedelta(seconds=130)).isoformat(), quantity=2, price='1500', fees='0')
        envelope['ledger'] = apply_retarget_event(state, event, now=accepted+timedelta(seconds=130))
        self.assertEqual(envelope['ledger']['cash'], '20200')
        self.assertEqual(envelope['ledger']['reserved_cash'], '171957/10')
        self.assertEqual(review_source_verified_retarget(envelope), envelope)

    def test_tampered_frozen_bytes_and_false_authentication_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            state, proposal, args = self.fixture(root)
            envelope = accept_retarget_with_execution_evidence(state, proposal, **args)
        altered = deepcopy(envelope)
        name = next(iter(altered['execution_evidence']['files']))
        altered['execution_evidence']['files'][name] = base64.b64encode(b'changed').decode()
        with self.assertRaisesRegex(ValueError, 'FROZEN_SOURCE_HASH_MISMATCH'):
            review_source_verified_retarget(altered)
        altered = deepcopy(envelope)
        altered['source_authenticated'] = True
        with self.assertRaisesRegex(ValueError, 'SOURCE_ENVELOPE_FIELDS_MISMATCH'):
            review_source_verified_retarget(altered)

    def test_expired_acceptance_is_not_revived_by_frozen_sources(self):
        with tempfile.TemporaryDirectory() as root:
            state, proposal, args = self.fixture(root)
            args['now'] += timedelta(seconds=121)
            with self.assertRaisesRegex(ValueError, 'CURRENT_REFERENCE_NOT_ACCEPTABLE'):
                accept_retarget_with_execution_evidence(state, proposal, **args)


if __name__ == '__main__':
    unittest.main()
