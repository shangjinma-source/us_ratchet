import json
from hashlib import sha256
from pathlib import Path
import tempfile
import time
import unittest

from backtest.bounded_research_process import run_worker


class BoundedResearchTests(unittest.TestCase):
    def test_success_is_not_research_pass_and_cannot_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root/'worker.py'
            script.write_text("print('done')\n", encoding='utf-8')
            arguments = dict(script=script, expected_sha256=sha256(script.read_bytes()).hexdigest(),
                             arguments=[], output_directory=root/'run', timeout_seconds=5)
            result = run_worker(**arguments)
            self.assertEqual(result['status'], 'WORKER_EXITED_REVIEW_REQUIRED')
            self.assertEqual(result['attempts'], 1)
            with self.assertRaises(FileExistsError):
                run_worker(**arguments)
            script.write_text("print('changed')\n", encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'FROZEN_PYTHON'):
                run_worker(**dict(arguments, output_directory=root/'another'))

    def test_timeout_stops_worker_and_its_child(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root/'worker.py'
            late = root/'late.txt'
            ready = root/'child-started.txt'
            child = "import time; from pathlib import Path; Path(%r).write_text('yes'); time.sleep(2); Path(%r).write_text('leaked')" % (str(ready), str(late))
            script.write_text('import subprocess, sys, time\nsubprocess.Popen([sys.executable, "-c", '+repr(child)+'])\ntime.sleep(30)\n', encoding='utf-8')
            result = run_worker(script=script, expected_sha256=sha256(script.read_bytes()).hexdigest(),
                                arguments=[], output_directory=root/'run', timeout_seconds=1)
            self.assertEqual(result['status'], 'TIMED_OUT_INCONCLUSIVE')
            self.assertTrue(ready.exists(), 'Child must actually have started to verify tree termination')
            time.sleep(2)
            self.assertFalse(late.exists())
            saved = json.loads((root/'run/status.json').read_bytes())
            self.assertEqual(saved['status'], 'TIMED_OUT_INCONCLUSIVE')


if __name__ == '__main__':
    unittest.main()
