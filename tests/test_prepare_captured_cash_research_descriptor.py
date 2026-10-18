import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts.prepare_captured_cash_research_descriptor import prepare
from hashlib import sha256


class DescriptorTests(unittest.TestCase):
    def test_unreviewed_package_writes_nothing(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            prep = b'{"status":"READY_CONDITIONAL"}'
            review = b'{"status":"PENDING"}'
            (root/'preparation.json').write_bytes(prep)
            (root/'review.json').write_bytes(review)
            with self.assertRaisesRegex(ValueError, 'INDEPENDENT_REVIEW_REQUIRED'):
                prepare(root=root, preparation_path='preparation.json',
                    preparation_sha256=sha256(prep).hexdigest(), review_path='review.json',
                    review_sha256=sha256(review).hexdigest(), output_directory='new')
            self.assertFalse((root/'new').exists())

    def test_unbound_pass_and_hash_drift_reject_without_output(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            prep = b'{}'; review = b'{"status":"PASS","source_hashes":{}}'
            (root/'preparation.json').write_bytes(prep)
            (root/'review.json').write_bytes(review)
            args = dict(root=root, preparation_path='preparation.json',
                preparation_sha256=sha256(prep).hexdigest(), review_path='review.json',
                review_sha256=sha256(review).hexdigest(), output_directory='new')
            with self.assertRaisesRegex(ValueError, 'REVIEW_ARTIFACT_BINDING_REQUIRED'):
                prepare(**args)
            args['preparation_sha256']='0'*64
            with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
                prepare(**args)
            self.assertFalse((root/'new').exists())

    def test_path_escape_before_read(self):
        with TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'UNSAFE_PATH'):
                prepare(root=folder, preparation_path='../preparation.json',
                    preparation_sha256='0'*64, review_path='review.json',
                    review_sha256='0'*64, output_directory='new')


if __name__ == '__main__': unittest.main()
