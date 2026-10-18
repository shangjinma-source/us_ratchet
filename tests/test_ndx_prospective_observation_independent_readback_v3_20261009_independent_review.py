"""Independent observation reader attacks; only synthetic temporary evidence."""
import ast
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_prospective_observation_independent_readback_v3_20261009 as reader
from scripts import ndx_prospective_observation_writer_v3_20261009 as writer
import test_ndx_prospective_observation_independent_readback_v3_20261009 as author_tests
from test_ndx_prospective_observation_writer_v3_20261009_independent_review import resolved, save


class IndependentObservationReaderTests(unittest.TestCase):
    def test_source_claims_must_be_exact_complete_original_set(self):
        for mode in ('extra','missing','changed'):
            with tempfile.TemporaryDirectory() as folder:
                values,producer,core=author_tests.evidence(Path(folder)/'attempt')
                claims=values['payload']['source_hash_claims']
                if mode=='extra':claims['forged-original']='f'*64
                elif mode=='missing':claims.pop(next(iter(claims)))
                else:claims[next(iter(claims))]='f'*64
                with patch.multiple(reader,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core),self.assertRaises(ValueError):
                    reader.inspect(**values)

    def test_every_mandatory_false_is_strict_for_all_evidence_roles(self):
        with tempfile.TemporaryDirectory() as folder:
            values,producer,core=author_tests.evidence(Path(folder)/'attempt')
            with patch.multiple(reader,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core):
                for role,keys in (('payload',set(reader.PAYLOAD_FALSE)|set(reader.WRITER_FALSE)),
                                  ('receipt',reader.WRITER_FALSE),('started',reader.WRITER_FALSE)):
                    for key in keys:
                        for value in (True,0,None):
                            values[role][key]=value
                            with self.subTest(role=role,key=key,value=value),self.assertRaises(ValueError):reader.inspect(**values)
                            values[role][key]=False

    def test_original_pointer_timezone_and_external_payload_anchor_cannot_drift(self):
        mutations=(lambda v:v['payload']['source_row_locations']['QQQ'].update(original_data_row_index=0),
                   lambda v:v['payload'].update(tzif_bytes_base64='AA=='),
                   lambda v:v['payload']['observation_identity'].update(session='2026-10-09'),
                   lambda v:v['payload_reference'].update(sha256='e'*64),
                   lambda v:v['receipt'].update(timing_classification='WITHIN_CONSERVATIVE_OBSERVATION_WINDOW'))
        for mutate in mutations:
            with tempfile.TemporaryDirectory() as folder:
                values,producer,core=author_tests.evidence(Path(folder)/'attempt','2026-10-09T13:30:00+00:00')
                mutate(values)
                with patch.multiple(reader,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core),self.assertRaises(ValueError):reader.inspect(**values)

    def test_formula_inspection_has_no_io_writer_or_core_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            values,producer,core=author_tests.evidence(Path(folder)/'attempt')
            with (patch.multiple(reader,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core),
                  patch.object(Path,'read_bytes',side_effect=AssertionError('Formula IO')),
                  patch.object(writer,'run',side_effect=AssertionError('Writer called'))):
                counts=reader.inspect(**values)
            self.assertEqual((counts['parent_typed_row_count'],counts['parent_gap_count'],counts['new_observation_count']),(69,8,1))
            self.assertFalse(counts['month_first_actual_observation'])
        tree=ast.parse(reader.SOURCE.read_bytes())
        names=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):names.append(node.module or '')
            elif isinstance(node,ast.Import):names.extend(x.name for x in node.names)
        self.assertFalse(any('prospective_observation' in name for name in names))

    def test_local_inventory_renamed_partial_original_attempt_and_drift(self):
        with tempfile.TemporaryDirectory() as root:
            research=Path(root);entry=resolved(research/'original');parent={'document':{'history':{'observations':[entry]}}}
            with patch.multiple(reader,RESEARCH=research,BASE=research/'current'):
                original=reader.local_inventory(parent,{})
                self.assertEqual(len(original),1)
                for version in ('V1','V2','V3'):
                    extra=research/'renamed';extra.mkdir();save(extra/'started.json',{'schema':'PROSPECTIVE_OBSERVATION_WRITER_STARTED_'+version})
                    with self.assertRaises(ValueError):reader.local_inventory(parent,{})
                    (extra/'started.json').unlink();extra.rmdir()
                save(research/'original/observation_payload.json',{'schema':'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1','observation_id':'f'*64})
                with self.assertRaises(ValueError):reader.local_inventory(parent,{})

    def test_source_hash_failure_namespace_symlink_and_live_claim_reject(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root);path=folder/'evidence';path.write_bytes(b'original');ref={'path':str(path),'sha256':reader.sha(b'original')}
            reader.consume(ref,{})
            path.write_bytes(b'drift')
            with self.assertRaises(ValueError):reader.consume(ref,{})
            path.write_bytes(b'original');(folder/'failure.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):reader.consume(ref,{})
            (folder/'failure.json').unlink();path.unlink();target=folder/'target';target.write_bytes(b'original')
            try:path.symlink_to(target)
            except OSError as error:self.skipTest(str(error))
            with self.assertRaises(ValueError):reader.consume(ref,{})
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Live read')):
            with self.assertRaises(ValueError):reader.consume({'path':str(reader.ROOT/'data/cache/QQQ.csv'),'sha256':'a'*64},{})


if __name__=='__main__':unittest.main()
