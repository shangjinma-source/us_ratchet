import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from scripts import ndx_double_c_resource_preflight_20261008 as preflight


class Tests(unittest.TestCase):
    def test_final_reader_and_unbound_registration_census(self):
        with patch.multiple(preflight.worker, LIFECYCLE_SHA=None, STREAM_SHA=None,
                            RESOURCE_PROOF_SHA=None, RESOURCE_CONTRACT_SHA=None,
                            RESOURCE_ENVELOPE=None):
            value=preflight.run()
        self.assertFalse(value['registration_census']['actual_file_authenticated'])
        self.assertEqual(value['reader_reference']['sha256'],preflight.reader.filehash(preflight.reader.SOURCE))
        self.assertEqual(value['registration_census']['document']['resource_proof_reference'],value['acceptance_reference'])
        self.assertLess(value['derived_request_json_upper'],1024**2)
        self.assertLess(value['derived_fixed_batch_json_upper'],8192)
        self.assertFalse(value['execution_authorized'])
        self.assertTrue(all(pin is None for pin in value['actual_pins'].values()))

    def test_actual_registration_text_and_tamper(self):
        witness=preflight.run()['registration_census']['document']
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'registration.json';path.write_bytes(preflight.worker.encode(witness))
            checked=preflight.run(path)
            self.assertTrue(checked['registration_census']['actual_file_authenticated'])
            witness['request_batch_limit']=1;path.write_bytes(preflight.worker.encode(witness))
            with self.assertRaises(AssertionError):preflight.run(path)
