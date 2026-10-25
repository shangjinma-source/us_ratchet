"""Read-only 36-month saved-frontier feasibility; no candidate economic replay."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.saved_frontier_tail_gate_audit import audit
from scripts.run_recent_continuous_probe import validate_selection_binding


def require(condition, message):
    if not condition:
        raise ValueError(message)


def diagnose(book_path, run_path, review_path):
    """Reject partial/mismatched artifacts before evaluating any candidate."""
    snapshots = {}

    def read(path):
        path = Path(path).resolve()
        if path not in snapshots:
            snapshots[path] = path.read_bytes()
        return snapshots[path]

    def document(path):
        return json.loads(read(path))

    def verify_sources(mapping):
        normalized = {}
        for name, expected in mapping.items():
            path = Path(name)
            path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
            actual = sha256(read(path)).hexdigest()
            require(actual == expected, 'SOURCE_HASH_MISMATCH:' + str(path))
            require(path not in normalized or normalized[path] == expected, 'CONFLICTING_SOURCE_HASH')
            normalized[path] = expected
        return normalized

    run_path, book_path = Path(run_path).resolve(), Path(book_path).resolve()
    require(book_path == run_path / 'book.json', 'BOOK_MUST_BELONG_TO_RUN')
    book, review = document(book_path), document(review_path)
    summary = document(run_path / 'summary.json')
    execution_path = run_path / 'execution_inputs.json'
    execution = document(execution_path)
    require(book['status'] == summary['status'] == 'COMPLETE', 'COMPLETE_BASELINE_REQUIRED')
    require(review['status'] == 'COMPLETE_DECLARED_INTERVAL_REVIEW_PASS'
            and review['original_book_status'] == 'COMPLETE', 'COMPLETE_INDEPENDENT_REVIEW_REQUIRED')
    require(not review['pending_decision_dates'] and not review['unexecuted_selection_dates']
            and review['removed_unexecuted_provider_audits'] == 0, 'NO_PENDING_PREFIX_ALLOWED')
    proof = review['proof']
    require(proof['selection_proof_checked'] is True and proof['selection_proofs_checked'] == 36
            and proof['expected_selection_proofs'] == 36 and proof['costs_checked'] is True
            and proof['risk_provider_certified'] is True, 'FULL_36_SELECTION_ACCOUNT_REVIEW_REQUIRED')
    pins = verify_sources(review['source_hashes'])
    require(book_path in pins and execution_path in pins, 'REVIEW_MUST_BIND_BOOK_AND_EXECUTION')
    require(summary['execution_inputs_sha256'] == sha256(read(execution_path)).hexdigest(),
            'RUN_EXECUTION_HASH_MISMATCH')
    assembled = execution['assembled']
    sessions = assembled['session_dates']
    require(sessions[0] == review['start'] == '2020-12-31'
            and sessions[-1] == review['end'] == review['requested_end'] == '2023-12-29',
            'FROZEN_FULL_INTERVAL_REQUIRED')
    require(sessions == sorted(set(sessions)) and len(sessions) == 754, 'FULL_SESSION_DOMAIN_REQUIRED')
    require([row['date'] for row in book['daily_ledger']] == sessions[1:]
            and review['executed_sessions'] == summary['completed_sessions'] == 753
            and proof['risk_sessions_checked'] == 753, 'FULL_EXECUTED_SESSIONS_REQUIRED')
    plans = assembled['monthly_inputs']
    dates = [plan['decision_date'] for plan in plans]
    months = ['2020-12'] + [f'{year}-{month:02d}' for year in (2021, 2022, 2023)
                          for month in range(1, 13) if (year, month) != (2023, 12)]
    require(len(dates) == 36 and dates == sorted(set(dates))
            and [day[:7] for day in dates] == months, 'FULL_36_MONTH_DOMAIN_REQUIRED')
    require(all(day in sessions for day in dates), 'DECISION_NOT_IN_SESSION_DOMAIN')
    verify_sources(assembled['source_hashes'])
    saved = [entry['selection'] for entry in book['provider_audit'] if entry.get('selection')]
    require(len(saved) == 36 and [s['raw_selection']['decision_date'] for s in saved] == dates,
            'BOOK_SELECTION_SEQUENCE_MISMATCH')
    raw_inputs = []
    for day, selection in zip(dates, saved):
        path = run_path / (day + '.selection.json')
        checkpoint = document(path)
        raw = checkpoint['raw_selection']
        require(raw == selection['raw_selection'], 'SAVED_RAW_BOOK_MISMATCH:' + day)
        validate_selection_binding(raw, checkpoint['arguments'])
        verify_sources(raw['binding']['source_hashes'])
        raw_inputs.append((day, raw))
    # All completeness/provenance gates above precede the first tail audit.
    rows = [dict(decision_date=day, **audit(raw)) for day, raw in raw_inputs]
    for path, content in snapshots.items():
        require(path.read_bytes() == content, 'SOURCE_CHANGED_DURING_AUDIT:' + str(path))
    return dict(status='COMPLETE_SAVED_FRONTIER_FEASIBILITY_AUDIT',
                rows=rows, decisions=36, changed_decisions=[r['decision_date'] for r in rows if r['changed']],
                cash_fallback_count=sum(r['changed_reason'] == 'NO_ELIGIBLE_STOCK_BASKET_CASH' for r in rows),
                selected_cash_count=sum(not any(r['target_quantities'].values()) for r in rows),
                source_hashes={str(path): sha256(content).hexdigest() for path, content in snapshots.items()},
                new_search_calls=0, execution_simulations=0, candidate_returns=None,
                economic_superiority_established=False,
                limitation='Baseline-account saved frontier diagnostic only; changed branch accounts need fresh authorized evaluation.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('book', 'run', 'review', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(args.book, args.run, args.review)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
