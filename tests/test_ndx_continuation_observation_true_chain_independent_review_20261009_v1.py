"""True temporary capture/observation chain attacks; requires a locked real R2.

One real candidate/writer fixture is shared to avoid rebuilding ancestors. Each
reader call still performs its original complete replay, without cache stubs.
Only disposable test reader artifacts are reset between independent attacks.
"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from ndx_continuation_observation_fixture_20261009_v1 import physical_continuation_candidate,run_writer,run_reader
from scripts import ndx_continuation_observation_writer_20261009_v1 as writer
from scripts import ndx_continuation_observation_independent_readback_20261009_v1 as reader


class TrueContinuationObservationIndependentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=TemporaryDirectory(prefix='TRUE_CONTINUATION_OBSERVATION_NEGATIVE_ONLY_')
        cls.root=Path(cls.temporary.name).resolve()
        cls.context=physical_continuation_candidate(cls.root)
        cls.payload_ref,cls.receipt_ref=run_writer(cls.context)
        cls.output=Path(cls.payload_ref['path']).parent
        cls.originals={name:(cls.output/name).read_bytes()for name in ('started.json','observation_payload.json','receipt.json')}
        cls.evidence=cls.root/'independent_attack_evidence';cls.evidence.mkdir()
        payload=reader.decode(cls.originals['observation_payload.json'])
        assert payload['sequence']==73 and payload['first_actual_observed_session_of_month']=='2026-10-02'

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def reset_own_reader(self):
        self.assertTrue(self.output.is_relative_to(self.root))
        for name in ('reader_started.json','independent_readback.json','failure.json'):
            path=self.output/name
            if path.exists():
                (self.evidence/(self.id().split('.')[-1]+'_'+name)).write_bytes(path.read_bytes())
                path.unlink()
        for name,raw in self.originals.items():(self.output/name).write_bytes(raw)

    def setUp(self):self.reset_own_reader()
    def tearDown(self):self.reset_own_reader()

    def test_a_real_reader_independent_math_and_current_never_read(self):
        original_compile=reader.compile_private;original_read=Path.read_bytes
        forbidden={reader.canonical_path(str(writer.SOURCE)),reader.canonical_path(str(reader.CORE))}
        calls=[]
        def compile_guard(path,*args,**kwargs):
            calls.append(str(path))
            if reader.canonical_path(str(path))in forbidden:raise AssertionError('Independent reader executes writer/generator')
            return original_compile(path,*args,**kwargs)
        def read_guard(path):
            if path in self.context['current'].values():raise AssertionError('Actual reader read mutable cache')
            return original_read(path)
        with patch.object(reader,'compile_private',side_effect=compile_guard),patch.object(Path,'read_bytes',read_guard):
            reference=run_reader(self.context,self.payload_ref,self.receipt_ref)
        report=reader.decode(Path(reference['path']).read_bytes());start=reader.decode((self.output/'reader_started.json').read_bytes())
        self.assertEqual(report['status'],'PASS');self.assertEqual(report['counts']['parent_typed_row_count'],72)
        self.assertEqual(len(report['reader_input_references']),13)
        self.assertEqual(report['reader_input_references'],start['reader_input_references'])
        for obj in (report,start):
            for key in reader.FLAGS:self.assertIs(obj[key],False)
        self.assertEqual({p.name for p in self.output.iterdir()},set(self.originals)|{'reader_started.json','independent_readback.json'})
        for path,sha in report['source_hashes'].items():self.assertEqual(reader.digest(Path(path).read_bytes()),sha)
        self.assertTrue(calls)

    def test_b_coordinated_source_only_extra_and_header_private_input_traps(self):
        trap=self.root/'UNCLASSIFIED_NEVER_READ.identity';trap.write_bytes(b'NO_READ_PERMISSION')
        trapref=reader.reference(str(trap),reader.digest(trap.read_bytes()))
        for attack in ('source_only_extra','unknown_metadata_contract','artifact_private_inputs'):
            with self.subTest(attack=attack):
                self.reset_own_reader()
                documents={name:reader.decode(raw)for name,raw in self.originals.items()}
                for value in documents.values():
                    value['source_hashes'][trapref['path']]=trapref['sha256']
                    if attack=='unknown_metadata_contract':value['consumer_metadata_contract_reference']=trapref
                    if attack=='artifact_private_inputs':value['reader_input_references']={'runtime':trapref}
                (self.output/'started.json').write_bytes(reader.encode(documents['started.json']))
                (self.output/'observation_payload.json').write_bytes(reader.encode(documents['observation_payload.json']))
                payload=reader.reference(str(self.output/'observation_payload.json'),reader.digest((self.output/'observation_payload.json').read_bytes()))
                documents['receipt.json']['payload_reference']=payload
                (self.output/'receipt.json').write_bytes(reader.encode(documents['receipt.json']))
                receipt=reader.reference(str(self.output/'receipt.json'),reader.digest((self.output/'receipt.json').read_bytes()))
                original_consume=reader.consume;original_read=Path.read_bytes
                def consume_guard(item,sources,**kwargs):
                    if item['path']==str(trap):raise AssertionError('Unclassified trap consume')
                    return original_consume(item,sources,**kwargs)
                def read_guard(path):
                    if path==trap:raise AssertionError('Unclassified trap read')
                    return original_read(path)
                with patch.object(reader,'consume',side_effect=consume_guard),patch.object(Path,'read_bytes',read_guard),self.assertRaises(ValueError):
                    run_reader(self.context,payload,receipt)
                self.assertFalse((self.output/'reader_started.json').exists())
                self.assertFalse((self.output/'independent_readback.json').exists())

    def test_c_reader_partial_and_postreport_own_or_ancestor_start_drift(self):
        (self.output/'reader_started.json').write_bytes(reader.encode(dict(schema='PROSPECTIVE_OBSERVATION_CONTINUATION_READER_STARTED_V1')))
        with self.assertRaisesRegex(ValueError,'namespace|inventory|attempt'):
            run_reader(self.context,self.payload_ref,self.receipt_ref)
        self.assertFalse((self.output/'independent_readback.json').exists())
        self.reset_own_reader()
        payload=reader.decode(self.originals['observation_payload.json'])
        ancestors=[Path(path)for path in payload['source_hashes']if Path(path).name=='started.json' and Path(path).parent!=self.output]
        self.assertTrue(ancestors,'Actual ancestor START must be in derived closure')
        ancestor=next((p for p in ancestors if 'registered_v4_root_observation' in str(p)),ancestors[0])
        original_ancestor=ancestor.read_bytes()
        for attack in ('own_start','ancestor_start'):
            with self.subTest(attack=attack):
                self.reset_own_reader();original_save=reader.save_bytes
                def save_guard(path,raw):
                    value=original_save(path,raw)
                    if path.name=='independent_readback.json':
                        target=self.output/'reader_started.json'if attack=='own_start'else ancestor
                        target.write_bytes(target.read_bytes()+b'\n')
                    return value
                try:
                    with patch.object(reader,'save_bytes',side_effect=save_guard),self.assertRaises(ValueError):
                        run_reader(self.context,self.payload_ref,self.receipt_ref)
                    failure=reader.decode((self.output/'failure.json').read_bytes())
                    self.assertEqual(failure['status'],'FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY')
                    self.assertIs(failure['retry_allowed'],False)
                    for key in reader.FLAGS:self.assertIs(failure[key],False)
                    self.assertTrue((self.output/'independent_readback.json').exists(),'Post-report failure must not discard original bytes')
                    with self.assertRaises(ValueError):run_reader(self.context,self.payload_ref,self.receipt_ref)
                finally:ancestor.write_bytes(original_ancestor)


if __name__=='__main__':unittest.main()
