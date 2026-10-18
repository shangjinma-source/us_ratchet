"""Synthetic lifecycle only: never project or evaluate an actual domain point."""
import json
from pathlib import Path
import unittest

from backtest import ndx_double_replacement_batch_lifecycle_research as lifecycle
from backtest import ndx_double_stream_resource_v3_research as resource
from scripts import ndx_double_replacement_stream_worker_20261008 as worker


class Tests(unittest.TestCase):
    def test_real_lifecycle_normal_terminal_fits_symbolic_frame(self):
        root = Path(__file__).resolve().parents[1]
        report = json.loads((root / 'tmp/double_stream_resource_v3_20261008_v3.json').read_bytes())
        end = 52406569
        start = end - 512
        descriptor = dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_DESCRIPTOR_V1', plan_sha256='f'*64, batch_index=5240, start=start, stop=end, point_count=512)
        plans = [dict(global_ordinal=start+i, task={'synthetic': i}) for i in range(512)]
        directory = 'C:\\CodexResearch\\us_ratchet\\01a0cc4a-c717-7813-843e-86aca0d15714\\double_replacement_stream_evaluation_c_20261008_v1\\batches\\005\\000005240'
        def reference(filename):
            return dict(path=directory + '\\' + filename, sha256='f'*64, byte_count=9999999999999999)
        saved = []
        result = dict(results=[dict(supplied_index=i, plan=plan, status='INFEASIBLE' if i%2 else 'FEASIBLE') for i, plan in enumerate(plans)])
        inspection = dict(status='PASS_SAVED_RESULT_EVIDENCE', supplied_plan_count=512)
        def complete(state):
            saved.append({'schema':'DOUBLE_REPLACEMENT_COMPRESSED_BATCH_RESULT_V1', **state, **worker.FLAGS})
            return reference('result.json')
        hooks = dict(before_dispatch=lambda:None, start=lambda _:reference('started.json'), evaluate=lambda _:result,
                     preserve=lambda _:reference('raw_receipt.json'), decode=lambda _:result,
                     inspect=lambda *_:(inspection, reference('inspection.json')), guard=lambda:None,
                     complete=complete, failure=lambda _:self.fail('Unexpected failure'))
        state = lifecycle.run_once(descriptor=descriptor, plans=plans, hooks=hooks)
        self.assertEqual(len(state['point_runs']),512)
        self.assertNotIn('completion',saved[0]['references'])
        encoded = resource.encode(saved[0])
        self.assertLessEqual(len(encoded),report['batch_fixed_metadata']['result.json']+512*67)
        self.assertEqual(set(saved[0]), {'schema','descriptor','started','call_invoked','returned','raw_preserved','independently_inspected','references','point_runs','automatic_retry_allowed','status'} | set(worker.FLAGS))


if __name__ == '__main__':
    unittest.main()
