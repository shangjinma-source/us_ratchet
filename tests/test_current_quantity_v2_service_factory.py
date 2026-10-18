from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from data.current_quantity_v2_service_factory import create_service


class FactoryTests(unittest.TestCase):
    def test_configuration_is_pinned_and_construction_does_not_search(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'descriptor.json'
            payload = dict(input_path='input.json', admission_path='admission.json', source_hashes={})
            raw = json.dumps(payload).encode()
            path.write_bytes(raw)
            with patch('data.current_quantity_portfolio_research_v2.subprocess.run') as worker:
                service = create_service(root=directory, descriptor_path=path.name,
                                         descriptor_sha256=sha256(raw).hexdigest())
                self.assertEqual(service.loader(), payload)
                worker.assert_not_called()
                path.write_bytes(raw + b' ')
                with self.assertRaisesRegex(ValueError, 'DESCRIPTOR_CHANGED'):
                    service.loader()
                worker.assert_not_called()

    def test_configuration_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in ('../descriptor.json', 'C:/descriptor.json', '/descriptor.json'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    create_service(root=directory, descriptor_path=path, descriptor_sha256='a' * 64)


if __name__ == '__main__':
    unittest.main()
