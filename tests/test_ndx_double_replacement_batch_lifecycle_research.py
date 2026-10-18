import unittest
from copy import deepcopy
from backtest.ndx_double_replacement_batch_lifecycle_research import run_once


class BatchLifecycleTests(unittest.TestCase):
    def fixture(self, statuses=('FEASIBLE', 'INFEASIBLE')):
        events = []
        plans = [dict(global_ordinal=i, task=dict(task_id=str(i))) for i in range(len(statuses))]
        descriptor = dict(start=0, stop=len(plans), point_count=len(plans))
        value = dict(results=[dict(supplied_index=i, plan=p, status=s) for i, (p, s) in enumerate(zip(plans, statuses))])
        saved = {}
        def step(name, result=None):
            def call(*args):
                events.append(name)
                return deepcopy(result)
            return call
        def preserve(result):
            events.append('preserve'); saved['raw'] = deepcopy(result); return 'raw'
        hooks = dict(before_dispatch=step('before'), start=step('start', 'started'),
                     evaluate=step('evaluate', value), preserve=preserve,
                     decode=lambda _: (events.append('decode') or deepcopy(saved['raw'])),
                     inspect=step('inspect', (dict(status='PASS_SAVED_RESULT_EVIDENCE', supplied_plan_count=len(plans)), 'inspection')),
                     guard=step('guard'), complete=step('complete', 'completion'), failure=step('failure', 'failure'))
        return descriptor, plans, hooks, events, saved

    def test_raw_first_full_batch(self):
        d,p,h,e,s = self.fixture()
        result = run_once(descriptor=d, plans=p, hooks=h)
        self.assertEqual(e, ['before','start','evaluate','preserve','decode','inspect','guard','complete'])
        self.assertEqual(result['status'], 'COMPLETE_SAVED_AND_INSPECTED')
        self.assertTrue(result['returned'] and result['raw_preserved'])

    def test_resource_stop_zero_calls(self):
        d,p,h,e,s = self.fixture()
        def stop(): raise MemoryError('resource')
        h['before_dispatch'] = stop
        result = run_once(descriptor=d, plans=p, hooks=h)
        self.assertEqual(e, ['failure']); self.assertFalse(result['call_invoked'])
        self.assertEqual(result['point_runs'], [])

    def test_returned_raw_before_inspector_failure_or_drift(self):
        for where in ('inspect','guard'):
            d,p,h,e,s = self.fixture()
            def fail(*args): raise ValueError('reject')
            h[where] = fail
            result = run_once(descriptor=d, plans=p, hooks=h)
            self.assertEqual(result['status'], 'VALIDATION_FAILURE')
            self.assertIn('raw',s); self.assertEqual(e.count('evaluate'),1)
            self.assertEqual(result['point_runs'][0]['status'], 'validation_failure_returned')

    def test_base_exception_and_broken_string(self):
        class Broken(BaseException):
            def __str__(self): raise RuntimeError('broken')
        d,p,h,e,s = self.fixture()
        def fail(*args): raise Broken()
        h['evaluate'] = fail
        result = run_once(descriptor=d, plans=p, hooks=h)
        self.assertFalse(result['returned']); self.assertFalse(result['raw_preserved'])
        self.assertEqual(result['status'],'UNKNOWN_RETURN_OR_PARTIAL_RAW')
        self.assertEqual(result['error']['message'],'ERROR_STRING_FAILED: RuntimeError')

    def test_non_json_return_preservation_failure_never_inspects(self):
        d,p,h,e,s = self.fixture()
        h['evaluate'] = lambda _: object()
        def fail(value): e.append('preserve'); raise TypeError('nonjson')
        h['preserve'] = fail
        result = run_once(descriptor=d, plans=p, hooks=h)
        self.assertTrue(result['returned']); self.assertFalse(result['raw_preserved'])
        self.assertNotIn('inspect',e); self.assertNotIn('decode',e)

    def test_technical_partition_not_infeasible(self):
        d,p,h,e,s = self.fixture(('FEASIBLE','EVALUATION_EXCEPTION','NOT_EVALUATED_TECHNICAL_STOP'))
        result = run_once(descriptor=d,plans=p,hooks=h)
        self.assertEqual(result['status'],'SAVED_TECHNICAL_STOP')
        self.assertEqual([r['status'] for r in result['point_runs']],['inspected_feasible','evaluation_exception','supplied_not_evaluated_technical'])
        self.assertEqual(e.count('evaluate'),1)

    def test_reordered_or_missing_input_rejected_before_hooks(self):
        d,p,h,e,s = self.fixture()
        with self.assertRaises(ValueError): run_once(descriptor=d,plans=list(reversed(p)),hooks=h)
        with self.assertRaises(ValueError): run_once(descriptor=d,plans=p[:-1],hooks=h)
        self.assertEqual(e,[])


if __name__ == '__main__': unittest.main()
