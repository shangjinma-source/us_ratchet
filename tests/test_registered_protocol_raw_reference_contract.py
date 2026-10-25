"""Independent reference-type regression; no registration or account writes."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import test_registered_quantity_v2_paper_protocol as fixtures
from data.registered_quantity_v2_paper_protocol import validate_registration_request


class RawReferenceTests(unittest.TestCase):
    def test_raw_evidence_is_verified_and_drift_still_rejected(self):
        with TemporaryDirectory() as folder:
            args, request, save = fixtures.fixture(folder)
            root = Path(folder)
            raw = b'\x00\xff\x01'; (root/'capture.bin').write_bytes(raw)
            ref = dict(path='capture.bin', sha256=sha256(raw).hexdigest())
            request['refs']['protocol'] = save('protocol.json', dict(evidence=[ref]))
            approval = json.loads((root/'auth.json').read_bytes())
            approval['protocol_sha256'] = request['refs']['protocol']['sha256']
            request['refs']['authorization'] = save('auth.json', approval)
            args['expected_request_sha256'] = save('request.json', request)['sha256']
            checked = validate_registration_request(**args)
            self.assertEqual(checked['verified_source_hashes'][str(root/'capture.bin')], ref['sha256'])
            (root/'capture.bin').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
                validate_registration_request(**args)

    def test_required_protocol_with_binary_suffix_cannot_bypass_json_validation(self):
        with TemporaryDirectory() as folder:
            args, request, save = fixtures.fixture(folder)
            raw = b'not a JSON protocol'; (Path(folder)/'protocol.bin').write_bytes(raw)
            request['refs']['protocol'] = dict(path='protocol.bin', sha256=sha256(raw).hexdigest())
            args['expected_request_sha256'] = save('request.json', request)['sha256']
            with self.assertRaises((ValueError, TypeError)):
                validate_registration_request(**args)


if __name__ == '__main__': unittest.main()
