"""Independent raw-binding attacks, without changing frozen probe evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from backtest import ndx_identity_raw_fact_research as facts
from scripts import ndx_identity_raw_fact_probe as cli


def rehashed_copy(directory, transform):
    manifest = json.loads(cli.MANIFEST.read_bytes())
    for probe in manifest['probes']:
        if probe['response_path'] is None:
            continue
        raw = Path(probe['response_path']).read_bytes()
        if probe['name'] == 'openfigi_cusip_mapping':
            payload = json.loads(raw)
            transform(probe['request'], payload)
            raw = json.dumps(payload, allow_nan=False).encode()
        path = Path(directory) / Path(probe['response_path']).name
        path.write_bytes(raw)
        probe.update(response_path=str(path), response_bytes=len(raw), response_sha256=hashlib.sha256(raw).hexdigest())
    path = Path(directory) / 'manifest.json'
    raw = json.dumps(manifest, allow_nan=False).encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


class RawFactIndependentReview(unittest.TestCase):
    def test_rehashed_body_and_manifest_cannot_accept_conflicting_cusip_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            def conflict(request, payload):
                payload[0]['data'][0]['cusip'] = request['json_payload'][1]['idValue']
            path, digest = rehashed_copy(directory, conflict)
            with self.assertRaises(ValueError):
                facts.extract_bound_probe(manifest_path=path, expected_sha256=digest)

    def test_rehashed_well_formed_fabricated_response_is_not_authentication(self):
        with tempfile.TemporaryDirectory() as directory:
            def fabricated(request, payload):
                payload[0]['data'][0]['name'] = 'SYNTHETIC FABRICATED DISPLAY NAME'
            path, digest = rehashed_copy(directory, fabricated)
            result = facts.extract_bound_probe(manifest_path=path, expected_sha256=digest)
            self.assertFalse(result['source_authenticity_adjudicated'])
            self.assertFalse(result['provider_to_historical_security_binding_verified'])
            self.assertFalse(result['historical_information_availability_verified'])
            self.assertFalse(result['point_in_time_verified'])
            self.assertFalse(result['promotion_allowed'])
            self.assertFalse(result['execution_performed'])
            self.assertTrue(all(row['security_issuer_cik'] is None for row in result['nport']['holdings'].values()))

    def test_position_only_no_echo_response_is_not_historical_identity_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            def reordered(request, payload):
                payload[0], payload[1] = deepcopy(payload[1]), deepcopy(payload[0])
            path, digest = rehashed_copy(directory, reordered)
            result = facts.extract_bound_probe(manifest_path=path, expected_sha256=digest)
            self.assertFalse(result['provider_to_historical_security_binding_verified'])
            for row in result['current_cusip_references'].values():
                self.assertFalse(row['historical_mapping_verified'])
                self.assertFalse(row['response_cusip_echo_present'])
                self.assertIsNone(row['fact_valid_interval'])


if __name__ == '__main__':
    unittest.main()
