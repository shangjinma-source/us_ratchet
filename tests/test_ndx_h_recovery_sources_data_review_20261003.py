"""Temporary source-chain attacks only. Never read actual H data or run recovery."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_h_failed_export_recovery_sources_20261003 as m
from test_ndx_h_failed_export_recovery_sources_20261003 import physical_fixture


def write(path, obj):
    raw=json.dumps(obj,ensure_ascii=False).encode();path.write_bytes(raw)
    return dict(path=str(path),sha256=sha256(raw).hexdigest())


def reanchor_role(refs,parent,role,change):
    path=Path(refs[role]['path']);d=json.loads(path.read_bytes());change(d)
    refs[role]=write(path,d);(parent/'sources'/f'{role}.json').write_bytes(path.read_bytes())
    started=json.loads((parent/'started.json').read_bytes())
    started['input_references'][role]=deepcopy(refs[role]);started['source_hashes'][str(path)]=refs[role]['sha256']
    refs['started']=write(parent/'started.json',started)


class Review(unittest.TestCase):
    def test_resigned_failed_b6_audit_and_publication_refused(self):
        for role in ('audit','publication'):
            with self.subTest(role=role),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);refs,codes,parent=physical_fixture(root)
                reanchor_role(refs,parent,role,lambda d:d.update(status='FAILED'))
                with patch.multiple(m,ROOT=root,PARENT=parent,BOUND=refs,CODE=codes):
                    with self.assertRaises(ValueError):m.load_sources()

    def test_postread_existing_parent_drift_not_only_inventory_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);refs,codes,parent=physical_fixture(root); original=m.private_core
            def private(r):
                n=original(r)
                if 'plan_failed_export_recovery' in n:
                    call=n['plan_failed_export_recovery']
                    def drifting(**kwargs):
                        result=call(**kwargs)
                        (parent/'navigation_expected_cells.jsonl').write_bytes(b'late source drift\n')
                        return result
                    n['plan_failed_export_recovery']=drifting
                return n
            with patch.multiple(m,ROOT=root,PARENT=parent,BOUND=refs,CODE=codes),patch.object(m,'private_core',side_effect=private):
                with self.assertRaisesRegex(ValueError,'changed|drift'):m.load_sources()

    def test_resigned_chart_identity_and_record_mapping(self):
        for field in ('task_ids','source_record'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);refs,codes,parent=physical_fixture(root)
                directory=parent/'attempts/attempt-00000'
                path=directory/'chart_source_index.json';chart=json.loads(path.read_bytes())
                if field=='task_ids':chart['task_ids'][0]='f'*64
                else:chart['source_jsonl_records'][0]['source_record']['byte_stop']+=1
                chart_ref=write(path,chart)
                pending_path=directory/'pending.json';pending=json.loads(pending_path.read_bytes())
                pending['chart_source_index_reference']=chart_ref;write(pending_path,pending)
                with patch.multiple(m,ROOT=root,PARENT=parent,BOUND=refs,CODE=codes):
                    with self.assertRaises(ValueError):m.load_sources()

    def test_loaded_code_and_original_data_namespace(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);refs,codes,parent=physical_fixture(root)
            altered=root/'altered_source.py';altered.write_bytes(Path(m.__file__).read_bytes()+b'\n# changed after import\n')
            with patch.multiple(m,ROOT=root,PARENT=parent,BOUND=refs,CODE=codes),patch.object(m,'__file__',str(altered)),patch.object(m,'SOURCE',altered,create=True):
                with self.assertRaisesRegex(ValueError,'[Ll]oaded|[Ss]elf|[Ss]ource'):m.load_sources()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);refs,codes,parent=physical_fixture(root)
            (Path(refs['index']['path']).parent/'unexpected.bin').write_bytes(b'unknown')
            with patch.multiple(m,ROOT=root,PARENT=parent,BOUND=refs,CODE=codes):
                with self.assertRaises(ValueError):m.load_sources()


if __name__=='__main__':unittest.main()
