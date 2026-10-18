import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_first_persisted_candidate_calendar_v2_20261003 as producer
from test_ndx_first_calendar_published_history_v2_20261003 import physical


class RootReview(unittest.TestCase):
    def test_late_prior_namespace_intrusion_is_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            bindings = physical(Path(folder))
            original = producer.save

            def save(path, value, **kwargs):
                reference = original(path, value, **kwargs)
                if path.name == 'publication.json':
                    (bindings['FAILED_PARENT'] / 'unexpected.json').write_text('{}')
                return reference

            with ExitStack() as stack:
                for key, value in bindings.items():
                    stack.enter_context(patch.object(producer, key, value))
                stack.enter_context(patch.object(producer, 'now', return_value='2026-10-02T20:02:00+00:00'))
                stack.enter_context(patch.object(producer, 'save', side_effect=save))
                with self.assertRaises(ValueError):
                    producer.run(execute=True)
                self.assertTrue((producer.OUTPUT / 'failure.json').exists())
                self.assertTrue((producer.OUTPUT / 'publication.json').exists())
                with self.assertRaises(ValueError):
                    producer.run(execute=True)


if __name__ == '__main__':
    unittest.main()
