import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_delta_paired_snapshot_full_independent_audit as audit


class FullReadbackTests(unittest.TestCase):
    def test_end_and_publication_source_or_gap_drift_rejected(self):
        for kind in ('source','gap'):
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'evidence.txt';path.write_bytes(b'old')
                sources=dict(audit.LOADED);gaps=[]
                if kind=='source':sources[str(path)]=hashlib.sha256(b'old').hexdigest()
                else:gaps=[dict(path=str(path),observed_current_sha256=hashlib.sha256(b'old').hexdigest())]
                audit.verify_sources_and_gaps(sources,gaps)
                path.write_bytes(b'new')
                with self.assertRaises(AssertionError):audit.verify_sources_and_gaps(sources,gaps)
                path.write_bytes(b'old')
                report=dict(source_hashes=sources,tasks=[dict(gap=x) for x in gaps])
                original_dump=json.dump
                def drift(*args,**kwargs):
                    original_dump(*args,**kwargs);path.write_bytes(b'new')
                with patch.object(audit.json,'dump',side_effect=drift):
                    with self.assertRaises(AssertionError):audit.publish_report(Path(directory)/'audit.json',report)

    def test_real_two_task_index_cannot_claim_full614(self):
        path=audit.FOLDER/'tasks/index_f70142afc0d36ab67046239566c8037d5f2652c0e149359a588f71440b22f362.json'
        with self.assertRaises(AssertionError):
            audit.audit_complete(path,'fcbdbb99dca8b11465106f29f58ec1424de1fcc3df3783f4d2d67d63491aceb9')

    def test_wrong_external_sha_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'index.json';path.write_text('{}')
            with self.assertRaises(AssertionError):audit.audit_complete(path,'0'*64)

    def test_forged_complete_flag_cannot_hide_incomplete_finalization(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'index.json'
            value=dict(schema='ndx_delta_paired_snapshot_completion_index_v1',planned=614,completed=[{}]*614,status='COMPLETE',
                       finalization=dict(completed=2,planned=614,status='PARTIAL',source_closure_verified=True))
            raw=json.dumps(value).encode();path.write_bytes(raw)
            with self.assertRaises(AssertionError):audit.audit_complete(path,hashlib.sha256(raw).hexdigest())


if __name__=='__main__':unittest.main()
