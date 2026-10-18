import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_double_replacement_compressed_independent_readback_20261008 as reader


class SourceReaderTests(unittest.TestCase):
    def test_pending_before_source_io(self):
        with patch.object(reader,'read',side_effect=AssertionError('no IO')):
            with self.assertRaisesRegex(ValueError,'Bind actual immutable'):
                reader.readback(registration_path='missing',registration_sha256='1'*64,execute=True)

    def test_failed_request_rejected_even_with_result_and_publication(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);request=root/'requests/request-000000';request.mkdir(parents=True)
            for path in (request/'result.json',request/'failure.json',root/'publication.json'):path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'Failed request namespace'):
                reader.namespace_gate(root,request,{})

    def test_exact_inventory_rejects_extra_or_changed_saved_bytes(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);request=root/'requests/request-000000';request.mkdir(parents=True)
            (request/'started.json').write_text('{}')
            result=dict(output_inventory_before_result=reader.inventory(root),partition=dict(full_domain_complete=False))
            (request/'result.json').write_text(json.dumps(result))
            self.assertEqual(len(reader.namespace_gate(root,request,result)),2)
            (request/'started.json').write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError,'inventory bytes'):reader.namespace_gate(root,request,result)
            (request/'started.json').write_text('{}');(root/'publication.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'file namespace'):reader.namespace_gate(root,request,result)


if __name__=='__main__':unittest.main()
