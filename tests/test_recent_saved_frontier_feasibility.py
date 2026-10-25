from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.audit_recent_saved_frontier_feasibility import diagnose
from test_saved_frontier_tail_gate_audit import fixture


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, separators=(',', ':')), encoding='utf-8')
    return sha256(path.read_bytes()).hexdigest()


def synthetic_run(root):
    source = root / 'synthetic_source.json'
    pins = {str(source): write(source, {'synthetic': True})}
    days = []
    day = date(2020, 12, 31)
    while day <= date(2023, 12, 29):
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    # Synthetic session fixture, not asserted to be the exchange calendar.
    excess = len(days) - 754
    days = days[:100] + days[100 + excess:]
    months = ['2020-12'] + [f'{y}-{m:02d}' for y in (2021, 2022, 2023)
                          for m in range(1, 13) if (y, m) != (2023, 12)]
    decisions = [next(d for d in days if d.startswith(month)) for month in months]
    selections = []
    for decision in decisions:
        raw = fixture()
        binding = raw['binding']
        arguments = binding['search_arguments']
        raw['decision_date'] = binding['decision_date'] = arguments['decision_date'] = decision
        raw['search_result']['decision_date'] = decision
        arguments['scenario_dates'] = [f'2020-{m:02d}-01' for m in range(1, 13)]
        raw['search_result']['scenario_dates'] = arguments['scenario_dates']
        binding['source_hashes'] = pins
        for quote in binding['valuation_quotes'].values():
            quote.update(as_of=decision, source_references=[str(source)])
        raw['decision_id'] = sha256(json.dumps(binding, sort_keys=True, separators=(',', ':'),
                                              ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        checkpoint_args = dict(decision_date=decision,
            account_state=dict(cash=binding['available_cash'], reserved_cash='0', shares={},
                               revision=binding['state_revision']), source_hashes=pins,
            valuation_quotes=[dict(security_id=sid, **q) for sid, q in binding['valuation_quotes'].items()],
            search_arguments=dict(arguments, quote_as_of=decision, price_basis='SYNTHETIC_USD'))
        write(root / (decision + '.selection.json'), dict(arguments=checkpoint_args, raw_selection=raw))
        selections.append(dict(selection=dict(raw_selection=raw)))
    book = dict(status='COMPLETE', daily_ledger=[dict(date=d) for d in days[1:]], provider_audit=selections)
    book_path = root / 'book.json'
    book_hash = write(book_path, book)
    execution_path = root / 'execution_inputs.json'
    execution_hash = write(execution_path, dict(assembled=dict(session_dates=days,
        monthly_inputs=[dict(decision_date=d) for d in decisions], source_hashes=pins)))
    write(root / 'summary.json', dict(status='COMPLETE', completed_sessions=753,
                                      execution_inputs_sha256=execution_hash))
    review = dict(status='COMPLETE_DECLARED_INTERVAL_REVIEW_PASS', original_book_status='COMPLETE',
        pending_decision_dates=[], unexecuted_selection_dates=[], removed_unexecuted_provider_audits=0,
        start=days[0], end=days[-1], requested_end=days[-1], executed_sessions=753,
        proof=dict(selection_proof_checked=True, selection_proofs_checked=36, expected_selection_proofs=36,
                   costs_checked=True, risk_provider_certified=True, risk_sessions_checked=753),
        source_hashes={str(book_path): book_hash, str(execution_path): execution_hash})
    write(root / 'review.json', review)
    return book_path, root, root / 'review.json'


class FeasibilityArtifactTests(unittest.TestCase):
    def test_complete_synthetic_36_months_zero_search(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = synthetic_run(Path(directory))
            result = diagnose(*arguments)
            self.assertEqual(result['decisions'], 36)
            self.assertEqual(result['changed_decisions'], [])
            self.assertEqual(result['new_search_calls'], 0)
            self.assertIsNone(result['candidate_returns'])

    def test_partial_or_mismatched_artifacts_rejected_before_audit(self):
        for mutation in ('partial', 'review', 'source', 'raw', 'missing_month'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                args = synthetic_run(root)
                if mutation == 'partial':
                    b = json.loads(args[0].read_text()); b['status'] = 'BLOCKED'; write(args[0], b)
                elif mutation == 'review':
                    r = json.loads(args[2].read_text()); r['proof']['selection_proofs_checked'] = 35; write(args[2], r)
                elif mutation == 'source':
                    write(root / 'synthetic_source.json', {'changed': True})
                else:
                    path = root / '2020-12-31.selection.json'
                    if mutation == 'missing_month':
                        path.unlink()
                    else:
                        saved = json.loads(path.read_text()); saved['raw_selection']['target_quantities'] = {}; write(path, saved)
                with patch('scripts.audit_recent_saved_frontier_feasibility.audit') as audit:
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        diagnose(*args)
                    audit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
