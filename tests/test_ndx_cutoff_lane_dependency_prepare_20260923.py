import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_cutoff_lane_dependency_prepare_20260923 as runner
import test_ndx_cutoff_lane_dependency_research as fixtures


class RunnerTests(unittest.TestCase):
    def test_create_only_and_saved_source_closure(self):
        helper=fixtures.LaneTests()
        with tempfile.TemporaryDirectory() as folder:
            queue,*_=helper.fixture(folder)
            reference=helper.save(folder,'queue.json',queue)
            output=Path(folder)/'prepare.json'
            result=runner.run([reference['path']],[reference['sha256']],output)
            report=json.loads(output.read_bytes())
            self.assertEqual(result['decisions'],1)
            self.assertIn(reference['path'],report['prepare_source_hashes'])
            self.assertFalse(result['fit_performed'])
            with self.assertRaises(FileExistsError):
                runner.run([reference['path']],[reference['sha256']],output)

    def test_source_changed_during_prepare_does_not_publish(self):
        helper=fixtures.LaneTests()
        with tempfile.TemporaryDirectory() as folder:
            queue,*_=helper.fixture(folder)
            reference=helper.save(folder,'queue.json',queue)
            output=Path(folder)/'prepare.json'
            original=runner.core.prepare_lanes
            def mutate(references):
                result=original(references)
                Path(reference['path']).write_text('{}')
                return result
            with patch.object(runner.core,'prepare_lanes',side_effect=mutate):
                with self.assertRaisesRegex(ValueError,'Source changed'):
                    runner.run([reference['path']],[reference['sha256']],output)
            self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
