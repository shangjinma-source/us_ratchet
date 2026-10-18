"""Temporary complete chains; no actual registration or observation namespace."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import ndx_registered_observation_independent_readback_20261009_v1 as reader
from scripts import ndx_registered_observation_writer_20261009_v1 as writer
from scripts import ndx_prospective_observation_writer_v3_20261009 as oldwriter
from backtest import ndx_prospective_observation_parent_history_research_v4 as history
import test_ndx_registered_observation_writer_20261009_v1_independent_review as physical


def publish(root,research,parent,session,name='observation'):
    capture,current=physical.capture_chain(root,research,parent,session,name+'_capture')
    args,value=physical.registration(root,research,parent,capture,name)
    with patch.multiple(writer,RESEARCH=research,CURRENT=current),patch.object(writer,'now',side_effect=physical.clock('2026-10-09T20:02:00+00:00','2026-10-12T13:30:00+00:00')):
        receipt=writer.run(**args)
    output=Path(value['output_directory']);payload=dict(path=str(output/'observation_payload.json'),sha256=reader.sha((output/'observation_payload.json').read_bytes()))
    return dict(**args,payload_reference=payload,receipt_reference=receipt),current,output


class RegisteredObservationReaderTests(unittest.TestCase):
    def test_pending_writer_anchor_before_io_and_explicit_false(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            self.assertEqual(reader.readback(registration_path='E:/r.json',registration_sha256='a'*64,payload_reference={},receipt_reference={}),dict(status='NOT_EXECUTED'))
            with patch.object(reader,'WRITER_SHA',None),self.assertRaises(ValueError):reader.readback(registration_path='E:/r.json',registration_sha256='a'*64,
                payload_reference=dict(path='E:/p.json',sha256='a'*64),receipt_reference=dict(path='E:/rr.json',sha256='b'*64),execute=True)

    def test_live_claim_rejected_before_read(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'QQQ.csv';path.write_bytes(b'not evidence')
            with patch.object(reader,'CURRENT',{'QQQ':path,'SPY':Path(folder)/'SPY.csv'}),patch.object(Path,'read_bytes',side_effect=AssertionError('Live read')):
                with self.assertRaises(ValueError):reader.consume(dict(path=str(path),sha256='a'*64),{})

    def test_complete_physical_v3_v4_late_compatibility_no_core_execution(self):
        for version in ('v3','v4'):
            with self.subTest(version=version),TemporaryDirectory(prefix='SYNTHETIC_ONLY_registered_obs_reader_') as folder:
                root=Path(folder);research=root/'research';research.mkdir()
                parent=deepcopy(oldwriter.PARENT_BOUND)if version=='v3'else physical.parents.compact_parent(root,research)
                args,current,output=publish(root,research,parent,'2026-10-08'if version=='v3'else'2026-10-09')
                for path in current.values():path.write_bytes(b'changed after capture')
                original=Path.read_bytes;private=reader.private_module
                def forbid_live(path):
                    if path in current.values():raise AssertionError('Live read')
                    return original(path)
                def no_generators(path,raw,digest,replacements=()):
                    if Path(path)in (writer.CORE,writer.SOURCE):raise AssertionError('Generator executed')
                    result=private(path,raw,digest,replacements)
                    if hasattr(result,'append_observation_history_v4'):result.append_observation_history_v4=lambda **k:(_ for _ in()).throw(AssertionError('Append called'))
                    return result
                with patch.multiple(reader,RESEARCH=research,CURRENT=current,WRITER_SHA=writer.LOADED_SHA),patch.object(Path,'read_bytes',forbid_live),patch.object(reader,'private_module',side_effect=no_generators):
                    audit=reader.readback(**args)
                    with self.assertRaises(ValueError):reader.readback(**args)
                report=reader.decode(Path(audit['path']).read_bytes());payload=reader.decode(Path(args['payload_reference']['path']).read_bytes());receipt=reader.decode(Path(args['receipt_reference']['path']).read_bytes())
                self.assertEqual(report['schema'],'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3');self.assertEqual(report['status'],'PASS')
                self.assertEqual(report['writer_adapter_schema'],reader.ADAPTER);self.assertEqual(report['actual_parent_schema'],payload['actual_parent_schema'])
                self.assertEqual(report['counts']['timing_classification'],'LATE_OBSERVATION');self.assertFalse(report['counts']['month_first_actual_observation'])
                self.assertEqual(report['counts']['parent_typed_row_count'],69 if version=='v3'else 70)
                self.assertEqual({p.name for p in output.iterdir()},{'started.json','observation_payload.json','receipt.json','independent_readback.json'})
                env=reader.envelope(parent,{})
                obs=dict(payload=payload,receipt=receipt,audit=report,payload_reference=args['payload_reference'],receipt_reference=args['receipt_reference'],audit_reference=audit,
                    reader_reference=dict(path=str(reader.SOURCE),sha256=reader.LOADED))
                appended=history.append_observation_history_v4(parent=env,observation=obs)
                self.assertEqual(appended['typed_row_count'],70 if version=='v3'else 71)

    def test_resigned_payload_receipt_metadata_must_still_match_parent(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_registered_obs_mutation_') as folder:
            root=Path(folder);research=root/'research';research.mkdir();args,current,output=publish(root,research,deepcopy(oldwriter.PARENT_BOUND),'2026-10-08')
            p=reader.decode(Path(args['payload_reference']['path']).read_bytes());r=reader.decode(Path(args['receipt_reference']['path']).read_bytes())
            p['sequence']=71;pp=Path(args['payload_reference']['path']);pp.write_bytes(reader.enc(p));args['payload_reference']['sha256']=reader.sha(pp.read_bytes())
            r['payload_reference']=args['payload_reference'];rp=Path(args['receipt_reference']['path']);rp.write_bytes(reader.enc(r));args['receipt_reference']['sha256']=reader.sha(rp.read_bytes())
            with patch.multiple(reader,RESEARCH=research,CURRENT=current,WRITER_SHA=writer.LOADED_SHA),self.assertRaises(ValueError):reader.readback(**args)
            self.assertTrue((output/'failure.json').is_file());self.assertFalse((output/'independent_readback.json').exists())
            with patch.multiple(reader,RESEARCH=research,CURRENT=current,WRITER_SHA=writer.LOADED_SHA),self.assertRaises(ValueError):reader.readback(**args)

    def test_bounded_external_inventory_and_renamed_partial_attempt(self):
        parent=reader.envelope(oldwriter.PARENT_BOUND,{})
        with TemporaryDirectory() as folder:
            research=Path(folder);sources={}
            with patch.object(reader,'RESEARCH',research):inventory=reader.attempt_inventory(parent,sources,research/'next')
            self.assertEqual(len(inventory),1);reader.guard(sources)
            hidden=research/'unrelated';hidden.mkdir();(hidden/'started.json').write_bytes(reader.enc(dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V4')))
            with patch.object(reader,'RESEARCH',research),self.assertRaises(ValueError):reader.attempt_inventory(parent,{},research/'next')

    def test_private_source_binding_duplicate_json_and_createonly(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}'):
            with self.assertRaises(ValueError):reader.decode(raw)
        raw=b'from elsewhere import dependency\nvalue=dependency+1'
        result=reader.private_module('E:/synthetic.py',raw,reader.sha(raw),[('from elsewhere import dependency','dependency',2)])
        self.assertEqual(result.value,3)
        with self.assertRaises(ValueError):reader.private_module('E:/synthetic.py',raw+b' ',reader.sha(raw))
        with TemporaryDirectory() as folder:
            path=Path(folder)/'started.json';reader.save(path,{})
            with self.assertRaises(FileExistsError):reader.save(path,{})
            with patch.object(reader.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
                with self.assertRaises(ValueError):reader.save(path.parent/'independent_readback.json',{})
                reader.save(path.parent/'failure.json',dict(status='FAILED'))


if __name__=='__main__':unittest.main()
