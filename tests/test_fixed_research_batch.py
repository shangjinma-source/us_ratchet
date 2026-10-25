from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest.fixed_research_batch import run_batch


class FixedBatchTests(unittest.TestCase):
    def registration(self, script):
        digest = sha256(script.read_bytes()).hexdigest()
        worker = dict(script=str(script), script_sha256=digest, arguments=[])
        return dict(books=[dict(worker, id=name) for name in ['L-A', 'L-B', 'E-A', 'E-B']],
                    review=worker, total_seconds=10, new_book_cutoff_seconds=8,
                    source_sha256={str(script): digest})

    def test_zero_exit_without_artifact_stops_before_second_book(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root/'worker.py'
            script.write_text("print('no result')\n", encoding='utf-8')
            with self.assertRaises(FileNotFoundError):
                run_batch(registration=self.registration(script), output_directory=root/'run')
            saved = json.loads((root/'run/batch.json').read_bytes())
            self.assertEqual(saved['status'], 'FAILED_INCONCLUSIVE')
            self.assertEqual(len(saved['workers']), 1)
            self.assertFalse((root/'run/L-B').exists())

    def test_one_budget_and_new_book_cutoff(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root/'worker.py'
            script.write_text('# fixture\n', encoding='utf-8')
            elapsed = [0]
            received = []

            def worker(**arguments):
                received.append(arguments['timeout_seconds'])
                Path(arguments['arguments'][-1]).write_text(json.dumps(dict(status='COMPLETE', book_id='L-A')))
                elapsed[0] = 9
                return dict(status='WORKER_EXITED_REVIEW_REQUIRED')

            with patch('backtest.fixed_research_batch.time.monotonic', side_effect=lambda: elapsed[0]), \
                 patch('backtest.fixed_research_batch.run_worker', side_effect=worker):
                result = run_batch(registration=self.registration(script), output_directory=root/'run')
            self.assertEqual(received, [10])
            self.assertEqual(result['status'], 'BUDGET_STOP_INCONCLUSIVE')
            self.assertEqual([row['id'] for row in result['completed_books']], ['L-A'])

    def test_review_must_bind_all_actual_book_results(self):
        for wrong_hash in (False, True):
            with self.subTest(wrong_hash=wrong_hash), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                script = root/'worker.py'
                script.write_text('# fixture\n', encoding='utf-8')
                elapsed, budgets, hashes = [0], [], {}

                def worker(**arguments):
                    budgets.append(arguments['timeout_seconds'])
                    artifact = Path(arguments['arguments'][-1])
                    name = Path(arguments['output_directory']).name
                    if name == 'review':
                        document = dict(status='REVIEW_COMPLETE', reviewed_book_sha256={} if wrong_hash else hashes)
                    else:
                        document = dict(status='COMPLETE', book_id=name)
                    raw = json.dumps(document).encode()
                    artifact.write_bytes(raw)
                    if name != 'review':
                        hashes[name] = sha256(raw).hexdigest()
                    elapsed[0] += 1
                    return dict(status='WORKER_EXITED_REVIEW_REQUIRED')

                with patch('backtest.fixed_research_batch.time.monotonic', side_effect=lambda: elapsed[0]), \
                     patch('backtest.fixed_research_batch.run_worker', side_effect=worker):
                    if wrong_hash:
                        with self.assertRaisesRegex(ValueError, 'BIND_ALL_FOUR'):
                            run_batch(registration=self.registration(script), output_directory=root/'run')
                    else:
                        result = run_batch(registration=self.registration(script), output_directory=root/'run')
                        self.assertEqual(result['status'], 'ARTIFACTS_READY_FOR_ASSESSMENT')
                self.assertEqual(budgets, [10, 9, 8, 7, 6])


if __name__ == '__main__':
    unittest.main()
