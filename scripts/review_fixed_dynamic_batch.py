"""Review four saved books without invoking a selector or execution kernel."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.dynamic_independent_review import review_account, review_selection_inputs, review_reentry_journal, require, F


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch-directory', required=True)
    parser.add_argument('--result', required=True)
    args = parser.parse_args()
    output = Path(args.result)
    require(not output.exists(), 'new review result required')
    result = dict(status='RUNNING', reviewed_book_sha256={}, books={}, production_changes=False)
    try:
        for book_id in ('L-A', 'L-B', 'E-A', 'E-B'):
            raw = (Path(args.batch_directory)/(book_id+'-result.json')).read_bytes()
            document = json.loads(raw)
            require(document['status'] == 'COMPLETE' and document['book_id'] == book_id, 'book identity')
            bundle_raw = Path(document['bundle_path']).read_bytes()
            require(sha256(bundle_raw).hexdigest() == document['bundle_sha256'], 'bundle hash')
            bundle = json.loads(bundle_raw)
            def selection(day):
                return json.loads((Path(document['selection_directory'])/(day+'.json')).read_bytes())
            metrics = review_account(bundle, document)
            metrics.update(review_reentry_journal(bundle, document))
            metrics.update(review_selection_inputs(bundle, document, selection))
            result['books'][book_id] = metrics
            result['reviewed_book_sha256'][book_id] = sha256(raw).hexdigest()
            print(book_id, 'INDEPENDENT_REVIEW_PASSED', flush=True)
        result['window_comparisons'] = {}
        for window in ('L', 'E'):
            a, b = (result['books'][window+'-'+arm] for arm in ('A', 'B'))
            result['window_comparisons'][window] = (
                F(b['interval_return']) >= F(a['interval_return']) and
                F(b['max_close_drawdown']) <= F(a['max_close_drawdown']))
        result['historical_screen'] = 'PASS' if all(result['window_comparisons'].values()) else 'REJECT'
        result.update(status='REVIEW_COMPLETE', optimizer_calls=0, book_kernel_replays=0,
                      limitations='Conditional historical data; modeled next-open fills. Not PIT, OOS, broker execution, or dynamic-versus-monthly proof. No production promotion.')
    except Exception as error:
        result.update(status='REVIEW_FAILED_INCONCLUSIVE', detail=str(error), error_type=type(error).__name__)
        raise
    finally:
        output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
