import json
from pathlib import Path
import unittest
from scripts import ndx_non_equal_base_readback as readback
import test_ndx_non_equal_base_runner as runner_tests


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        helper = runner_tests.NonEqualBaseRunnerTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.helper = helper
        for task in helper.prepared['tasks']:
            task['training_semantics_sha256'] = helper.prepared['training_semantics']['training_semantics_sha256']
            task['job_id'] = readback.runner.preparation._sha({k:v for k,v in task.items() if k != 'job_id'})
        result = readback.runner.run(**helper.args, execute=True, max_new_tasks=1)
        self.path = Path(result['output_dir'])/'context.json'
        self.sha = result['context_sha256']

    def test_partial_then_complete_read_only(self):
        before = {p.name:p.read_bytes() for p in self.path.parent.iterdir()}
        result = readback.read_context(context_path=self.path, expected_context_sha256=self.sha)
        self.assertEqual((result['planned'],result['completed'],result['missing']), (2,1,1))
        self.assertEqual(result['status'],'PARTIAL')
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.path.parent.iterdir()})
        self.assertFalse(result['promotion_allowed'])
        readback.runner.run(**self.helper.args, execute=True, resume=True)
        result = readback.read_context(context_path=self.path, expected_context_sha256=self.sha)
        self.assertEqual((result['completed'],result['missing'],result['status']), (2,0,'COMPLETE'))

    def test_explicit_digest_and_corruption_rejected(self):
        for digest in ('', '0'*64):
            with self.assertRaises(ValueError):
                readback.read_context(context_path=self.path, expected_context_sha256=digest)
        checkpoint = next(p for p in self.path.parent.glob('*.json') if p != self.path)
        checkpoint.write_bytes(b'{}')
        with self.assertRaises(ValueError):
            readback.read_context(context_path=self.path, expected_context_sha256=self.sha)

    def test_rehashed_denominator_rejected(self):
        context = json.loads(self.path.read_bytes())
        context['planned'] = 3
        self.path.write_bytes(readback.runner._bytes(context))
        with self.assertRaisesRegex(ValueError,'denominator'):
            readback.read_context(context_path=self.path, expected_context_sha256=readback.runner._sha(context))


if __name__ == '__main__': unittest.main()
