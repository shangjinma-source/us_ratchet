"""Rehashed ledger corruption must reach and fail independent arithmetic."""
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_single_replacement_signed_paths_20261003 as publisher
from scripts import ndx_single_replacement_signed_paths_independent_readback_20261003 as reader
from test_ndx_single_replacement_signed_paths_20261003 import physical


class RootReaderReview(unittest.TestCase):
    def test_rehashed_cash_corruption_rejected_by_independent_ledger(self):
        with tempfile.TemporaryDirectory() as temporary, physical(Path(temporary)) as registration:
            outputs = publisher.run(registration_reference=registration, execute=True)

            def read(reference):
                return json.loads(Path(reference['path']).read_bytes())

            def rewrite(reference, value):
                path = Path(reference['path'])
                path.write_bytes(publisher.enc(value))
                return publisher.ref(path, publisher.filehash(path))

            result = read(outputs['result'])
            entry = result['rows'][0]
            raw = read(entry['raw_reference'])
            actual = raw['result']['rows'][0]
            actual['cash_after_usd'] = str(Fraction(actual['cash_after_usd']) + 1)
            entry['raw_reference'] = rewrite(entry['raw_reference'], raw)
            postcheck = read(entry['postcheck_reference'])
            postcheck['raw_reference'] = entry['raw_reference']
            entry['postcheck_reference'] = rewrite(entry['postcheck_reference'], postcheck)
            outputs['result'] = rewrite(outputs['result'], result)
            publication = read(outputs['publication'])
            publication['result_reference'] = outputs['result']
            outputs['publication'] = rewrite(outputs['publication'], publication)

            private = publisher.private

            def stream_only(role, data):
                self.assertEqual(role, 'stream', 'Reader must not compile production accounting')
                return private(role, data)

            with patch.object(reader, 'PUBLISHER_SHA', publisher.LOADED), \
                    patch.object(reader, 'OUTPUT', Path(temporary) / 'readback'), \
                    patch.object(publisher, 'private', stream_only):
                with self.assertRaisesRegex(ValueError, 'cash_after_usd'):
                    reader.readback(registration_reference=registration,
                                    result_reference=outputs['result'],
                                    publication_reference=outputs['publication'], execute=True)
                self.assertFalse((reader.OUTPUT / 'independent_readback.json').exists())
                failure = json.loads((reader.OUTPUT / 'failure.json').read_bytes())
                self.assertEqual(failure['completed_case_count'], 0)


if __name__ == '__main__':
    unittest.main()
