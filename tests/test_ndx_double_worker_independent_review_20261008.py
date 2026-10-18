"""Independent synthetic lifecycle review; never evaluates a real task."""
import unittest

import test_ndx_double_replacement_batch_lifecycle_research as fixture_module
from backtest import ndx_double_replacement_batch_lifecycle_research as lifecycle
from backtest import ndx_double_replacement_compressed_batch_research as codec
from scripts import ndx_double_replacement_compressed_worker_20261008 as worker


class Tests(unittest.TestCase):
    def test_full_domain_batch_denominators_without_task_evaluation(self):
        for size, count, tail in ((512, 102357, 297), (10000, 5241, 6569)):
            plan = codec.build_plan(preparation_reference=dict(path='synthetic', sha256='1'*64), prepared_content_sha256=worker.CONTENT, **worker.COUNTS, batch_size=size)
            self.assertEqual(plan['document']['batch_count'], count)
            last = codec.descriptor(plan, count-1)
            self.assertEqual(last['point_count'], tail)
            self.assertEqual(last['stop'], 52406569)
            partition = codec.partition(plan, [])
            self.assertEqual(partition['counts']['undispatched'], 52406569)
            self.assertFalse(partition['full_domain_complete'])

    def test_all_hook_failures_keep_exact_dispatch_state_without_retry(self):
        for name in ('before_dispatch', 'start', 'evaluate', 'preserve', 'decode', 'inspect', 'guard', 'complete'):
            descriptor, plans, hooks, events, saved = fixture_module.BatchLifecycleTests().fixture()
            counts = dict.fromkeys(hooks, 0)
            originals = dict(hooks)
            for key, function in originals.items():
                def counted(*args, key=key, function=function):
                    counts[key] += 1
                    if key == name:
                        raise OSError('synthetic failure')
                    return function(*args)
                hooks[key] = counted
            result = lifecycle.run_once(descriptor=descriptor, plans=plans, hooks=hooks)
            self.assertTrue(all(n <= 1 for n in counts.values()))
            self.assertEqual(counts['failure'], 1)
            self.assertFalse(result['independently_inspected'])
            self.assertEqual(result['call_invoked'], name not in ('before_dispatch', 'start'))
            preserved = name in ('decode', 'inspect', 'guard', 'complete')
            self.assertEqual(result['raw_preserved'], preserved)
            if preserved:
                self.assertIn('raw', saved)
                self.assertEqual(result['point_runs'], [dict(start=0, stop=2, status='validation_failure_returned')])
            elif result['call_invoked']:
                self.assertEqual(result['point_runs'], [dict(start=0, stop=2, status='unresolved_dispatch_or_raw')])
            else:
                self.assertEqual(result['point_runs'], [])

    def test_numeric_after_technical_is_not_published_as_success(self):
        for first in ('EVALUATION_EXCEPTION', 'NOT_EVALUATED_TECHNICAL_STOP', 'NOT_EVALUATED_BUDGET'):
            descriptor, plans, hooks, events, saved = fixture_module.BatchLifecycleTests().fixture((first, 'FEASIBLE'))
            result = lifecycle.run_once(descriptor=descriptor, plans=plans, hooks=hooks)
            self.assertEqual(result['status'], 'VALIDATION_FAILURE')
            self.assertEqual(events.count('evaluate'), 1)
            self.assertNotIn('complete', events)
            self.assertIn('raw', saved)

    def test_failure_metadata_write_failure_propagates_without_second_call(self):
        descriptor, plans, hooks, events, saved = fixture_module.BatchLifecycleTests().fixture()
        def fail(*args):
            raise OSError('synthetic disk failure')
        hooks['inspect'] = fail
        hooks['failure'] = fail
        with self.assertRaises(OSError):
            lifecycle.run_once(descriptor=descriptor, plans=plans, hooks=hooks)
        self.assertEqual(events.count('evaluate'), 1)
        self.assertIn('raw', saved)


if __name__ == '__main__':
    unittest.main()
