"""Bounded live-unit review; synthetic sources, no production account writes."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import importlib.util
import json
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from core.strategy_account_split_v1 import apply_event
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
import test_split_target_inputs_v1 as target_fixture
import test_strategy_account_unit_review as original

spec = importlib.util.spec_from_file_location('split_unit_candidate',
    Path(__file__).resolve().parents[1] / 'docs/candidates/strategy_account_split_unit_review.py')
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


def split_case(notice='Unrelated notice'):
    effective = '2026-10-16T13:30:00+00:00'
    epoch = int(datetime.fromisoformat(effective).timestamp())
    arguments = original.fixture(events={'splits': {str(epoch): dict(
        date=epoch, numerator=8, denominator=1, splitRatio='8:1')}}, held=True, notice=notice)
    action = dict(event_id='split', kind='SPLIT_CONFIRMED', action_id='action', security_id='S',
        ratio=8, effective_at=effective, broker_confirmed_at='2026-10-16T13:31:00+00:00',
        old_unit_id='old', new_unit_id='new', evidence_sha256='a'*64)
    state = arguments['state']
    arguments['state'], _ = apply_event(state, action, expected_revision=state['revision'])
    arguments['marks']['S'].update(unit_id='new', price='5/4')
    arguments['marks_sha256'] = sha256(canonical(arguments['marks'])).hexdigest()
    return arguments, action


class SplitUnitReviewTests(unittest.TestCase):
    def test_generated_review_flows_into_monthly_target_inputs(self):
        with TemporaryDirectory() as folder:
            arguments, before = target_fixture.SplitTargetInputsTests().case(folder)
            package = arguments['source_package']
            marks = json.loads(package['files'][arguments['marks_path']])
            for mark in marks.values():
                mark['captured_at'] = arguments['now']
            mark_hash = sha256(canonical(marks)).hexdigest()
            package['files'][arguments['marks_path']] = canonical(marks)
            package['source_hashes'][arguments['marks_path']] = mark_hash
            epoch = int(datetime.fromisoformat('2026-11-02T14:30:00+00:00').timestamp())
            def fetch(ticker, begin, end):
                events = {'splits': {str(epoch): dict(date=epoch, numerator=8, denominator=1, splitRatio='8:1')}} if ticker == 'AAA' else {}
                return dict(status=200, body=canonical(dict(chart=dict(error=None, result=[dict(
                    meta=dict(symbol=ticker, currency='USD', instrumentType='EQUITY'), events=events)]))))
            rss = b'<rss><channel><title>Nasdaq</title><item><title>Unrelated notice</title><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'
            sources = PaperActionEvidenceSources(fetch=fetch, rss_fetch=lambda: dict(status=200, body=rss),
                clock=lambda: datetime.fromisoformat(arguments['now']))
            securities = {'A': {'ticker': 'AAA'}, 'B': {'ticker': 'BBB'}}
            state = arguments['state']
            actions = sources.capture(dict(account_id=state['account_id'], state_revision=state['revision'],
                window_start='2026-10-29T20:00:00Z', observed_floor='2026-10-29T20:00:00Z',
                securities=securities, current_target_quantities={}))
            previous = json.loads(package['files'][arguments['unit_review_path']])
            review = candidate.review_interval(state=state, securities=securities, marks=marks,
                action_package=actions, marks_sha256=mark_hash, now=arguments['now'],
                training_manifest_sha256=previous['training_manifest_sha256'],
                historical_search_arguments_sha256=previous['historical_search_arguments_sha256'],
                historical_price_basis=before['binding']['historical_search_arguments']['price_basis'],
                training_closed_at=previous['training_closed_at'])
            for path, raw in actions['files'].items():
                self.assertNotIn(path, package['files'])
                package['files'][path] = raw
                package['source_hashes'][path] = actions['source_hashes'][path]
            target_fixture.SplitTargetInputsTests().review(arguments, review)
            result = target_fixture.candidate.build_target_inputs(**arguments)
            self.assertEqual(result['binding']['strategy_equity'], before['binding']['strategy_equity'])
            self.assertEqual(result['binding']['strategy_shares']['A'], 16)
            self.assertTrue(result['execution_blocked'])

    def test_matching_post_training_split_produces_bound_unit_review(self):
        arguments, action = split_case()
        saved = deepcopy(arguments)
        result = candidate.review_interval(**arguments)
        security = result['securities']['S']
        self.assertEqual(security['current_unit_id'], 'new')
        self.assertEqual(security['recorded_action_sha256'], sha256(canonical(action)).hexdigest())
        self.assertEqual(result['account_revision'], arguments['state']['revision'])
        for key in ('source_authenticated', 'broker_evidence_authenticated', 'coverage_complete', 'executable'):
            self.assertFalse(result[key])
        self.assertEqual(arguments, saved)

    def test_old_mark_and_in_training_split_remain_blocked(self):
        for mode, reason in [('unit', 'SPLIT_CURRENT_MARK_UNIT_REQUIRED'),
                             ('training', 'SPLIT_WITHIN_TRAINING_REQUIRES_HISTORY_REVIEW')]:
            arguments, _ = split_case()
            if mode == 'unit':
                arguments['marks']['S']['unit_id'] = 'old'
                arguments['marks_sha256'] = sha256(canonical(arguments['marks'])).hexdigest()
            else:
                arguments['training_closed_at'] = '2026-10-16T13:45:00+00:00'
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, reason):
                candidate.review_interval(**arguments)

    def test_recorded_action_does_not_bypass_official_notice_gate(self):
        arguments, _ = split_case(notice='AAA announces split')
        with self.assertRaisesRegex(ValueError, 'KNOWN_NOTICE_REQUIRES_REVIEW'):
            candidate.review_interval(**arguments)

    def test_original_unit_review_regressions_on_candidate(self):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(original.UnitReviewTests)
        with patch.object(original, 'review_interval', candidate.review_interval):
            result = unittest.TestResult()
            suite.run(result)
        self.assertEqual(result.testsRun, 5)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])


if __name__ == '__main__':
    unittest.main()
