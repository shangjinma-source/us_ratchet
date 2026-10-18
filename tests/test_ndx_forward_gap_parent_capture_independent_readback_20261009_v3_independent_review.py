"""Independent reader adversarial tests; no actual readback execution."""
import ast
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_forward_gap_parent_capture_independent_readback_20261009_v3 as reader
from test_ndx_forward_gap_parent_capture_research_v3 import fixture


def inspect(arguments):
    return reader.reconstruct_plan(**arguments,csv_rows=reader.private_csv_reader(reader.CSV_READER.read_bytes()))


class IndependentReaderReviewTests(unittest.TestCase):
    def test_parent_evidence_coordinated_attempt_and_duplicate_rejected(self):
        for mode in ('coordinated','duplicate','unresolved'):
            a=fixture();h=a['parent']['document']['history'];attempt=h['parent_attempt_inventory'][0]
            if mode=='coordinated':
                ref=deepcopy(h['observations'][0]['reader_reference'])
                h['observations'][0]['payload_reference']=ref;attempt['payload_reference']=deepcopy(ref)
            elif mode=='duplicate':h['parent_attempt_inventory'].append(deepcopy(attempt))
            else:h['parent_attempt_inventory'].append({'session':'2026-10-06','status':'STARTED'})
            with self.subTest(mode=mode),self.assertRaises(ValueError):inspect(a)

    def test_all_six_inner_parent_capture_reference_associations(self):
        for key in ('parent_history_reference','parent_publication_reference','parent_readback_reference',
                    'capture_reference','capture_publication_reference','capture_readback_reference'):
            a=fixture();ref=deepcopy(a['parent']['reader_reference']);a['parent']['document']['history'][key]=ref
            for role in ('document','publication','readback'):a['parent'][role]['source_hashes'][ref['path']]=ref['sha256']
            with self.subTest(key=key),self.assertRaises(ValueError):inspect(a)

    def test_optional_authority_and_unfinished_types_rejected(self):
        for role in ('document','publication','readback'):
            a=fixture();a['parent'][role]['production_generator_authorized']=True
            with self.subTest(role=role),self.assertRaises(ValueError):inspect(a)
        for value in (None,{},[{'session':'2026-10-08'}]):
            a=fixture();a['parent']['document']['history']['excluded_not_completed_source_sessions']=value
            with self.subTest(value=value),self.assertRaises(ValueError):inspect(a)

    def test_valid_alternate_timezone_hash_does_not_override_parent(self):
        a=fixture(['2026-10-08']);raw=Path('D:/python/Lib/site-packages/tzdata/zoneinfo/UTC').read_bytes()
        a['tzif_bytes']=raw;a['tzif_reference']={'path':'alternate-zone','sha256':reader.digest(raw)}
        with self.assertRaises(ValueError):inspect(a)

    def test_source_drift_namespace_and_mutable_cache_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source';path.write_bytes(b'original')
            item=reader.reference(str(path),reader.digest(b'original'));reader.consume(item,{})
            path.write_bytes(b'drift')
            with self.assertRaises(ValueError):reader.consume(item,{})
            path.unlink();path.mkdir()
            with self.assertRaises(ValueError):reader.namespace(Path(folder),('source',))
        with patch.object(reader,'consume',side_effect=AssertionError('Mutable bytes read')):
            with self.assertRaisesRegex(ValueError,'Mutable cache'):
                reader.guard({str(reader.ROOT/'data/cache/QQQ.csv'):'a'*64})

    def test_existing_output_pre_io_and_no_new_pure_import_or_exec(self):
        with tempfile.TemporaryDirectory() as folder:
            pins=dict.fromkeys(('PRODUCER_SHA','PURE_SHA','CAPTURE_SHA','PUBLICATION_SHA'),'a'*64)
            with (patch.multiple(reader,OUTPUT=Path(folder),**pins),
                  patch.object(Path,'read_bytes',side_effect=AssertionError('Source IO'))):
                with self.assertRaisesRegex(ValueError,'Create-only'):reader.readback(execute=True)
        tree=ast.parse(reader.SOURCE.read_bytes())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):self.assertNotIn('forward_gap_parent',node.module or '')
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='exec']
        self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
