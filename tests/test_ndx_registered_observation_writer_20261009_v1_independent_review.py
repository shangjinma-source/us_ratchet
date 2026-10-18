"""Registered writer full physical temporary chains and fail-closed attacks."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_registered_observation_writer_20261009_v1 as writer
from scripts import ndx_registered_forward_capture_independent_readback_20261009_v1 as capture_reader
from scripts import ndx_prospective_observation_writer_v3_20261009 as oldwriter
from backtest import ndx_observation_runtime_registration_research_v1 as registration_core
import test_ndx_registered_forward_capture_runtime_20261009_v1_independent_review as parents
import test_ndx_registered_forward_capture_independent_readback_20261009_v1_independent_review as captures


def capture_chain(root,research,parent,session,name):
    args,current,value=captures.publish(root,research,parent,session,name)
    with patch.multiple(capture_reader,RESEARCH=research,CURRENT=current):
        audited=capture_reader.readback(**args,output_directory=str(research/(name+'_audit')))
    return dict(reference=args['capture_reference'],publication_reference=args['publication_reference'],
        readback_reference=audited,reader_reference=dict(path=str(capture_reader.SOURCE),sha256=capture_reader.LOADED_SHA)),current


def registration(root,research,parent,capture,name):
    value=dict(schema=registration_core.SCHEMA,runtime_reference=dict(path=str(writer.SOURCE),sha256=writer.LOADED_SHA),
        dependency_references={key:dict(path=str(path),sha256=sha)for key,(path,sha)in writer.DEPENDENCIES.items()},
        parent=deepcopy(parent),capture=deepcopy(capture),output_directory=str(research/name),**registration_core.FLAGS)
    path=root/(name+'_registration.json');path.write_bytes(writer.encode(value))
    return dict(registration_path=str(path),registration_sha256=writer.sha(path.read_bytes()),execute=True),value


def clock(start,check):
    times=iter((start,start,check))
    return lambda:next(times,check)


class IndependentRegisteredObservationWriterTests(unittest.TestCase):
    def test_pending_all_host_anchors_before_io(self):
        for mode in ('registration','registration_core','reference_core',*writer.DEPENDENCIES):
            deps=deepcopy(writer.DEPENDENCIES)
            if mode in deps:deps[mode]=(deps[mode][0],None)
            with (self.subTest(mode=mode),patch.multiple(writer,DEPENDENCIES=deps,
                REGISTRATION_CORE=(writer.REGISTRATION_CORE[0],None if mode=='registration_core' else writer.REGISTRATION_CORE[1]),
                REFERENCE_CORE=(writer.REFERENCE_CORE[0],None if mode=='reference_core' else writer.REFERENCE_CORE[1])),
                patch.object(Path,'read_bytes',side_effect=AssertionError('IO before pending anchor'))):
                with self.assertRaises(ValueError):writer.run(registration_path='E:/synthetic_registration.json',
                    registration_sha256=None if mode=='registration' else 'a'*64,execute=True)

    def test_full_physical_v3_v4_late_and_actual_schema_without_live_reads(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_registered_observation_') as folder:
            root=Path(folder);research=root/'research';research.mkdir()
            cases=[('v3',deepcopy(oldwriter.PARENT_BOUND),'2026-10-08',70,'2026-10-09T20:03:00+00:00'),
                ('v4',parents.compact_parent(root,research),'2026-10-09',71,'2026-10-12T13:30:00+00:00')]
            for name,parent,session,sequence,check in cases:
                capture,current=capture_chain(root,research,parent,session,name+'_capture')
                args,value=registration(root,research,parent,capture,name+'_writer')
                real_read=Path.read_bytes
                def no_live(path):
                    if path in current.values():raise AssertionError('Writer current cache read')
                    return real_read(path)
                for path in current.values():path.write_bytes(b'changed since audited capture')
                with (patch.multiple(writer,RESEARCH=research,CURRENT=current),patch.object(Path,'read_bytes',no_live),
                    patch.object(writer,'now',side_effect=clock('2026-10-09T20:02:00+00:00',check)),
                    patch.dict('sys.modules',{'backtest.ndx_prospective_observation_receipt_research':SimpleNamespace(),
                        'backtest.ndx_prospective_observation_parent_history_research_v4':SimpleNamespace()})):
                    receipt_ref=writer.run(**args)
                    with self.assertRaisesRegex(ValueError,'Exclusive attempt'):writer.run(**args)
                output=Path(value['output_directory']);p=writer.decode((output/'observation_payload.json').read_bytes());r=writer.decode(Path(receipt_ref['path']).read_bytes())
                self.assertEqual(p['sequence'],sequence);self.assertEqual(p['session'],session)
                self.assertEqual(p['actual_parent_schema'],writer.decode(Path(parent['reference']['path']).read_bytes())['history']['schema'])
                self.assertEqual(p['writer_adapter_schema'],writer.ADAPTER)
                self.assertFalse(p['month_first_actual_observation']);self.assertEqual(r['timing_classification'],'LATE_OBSERVATION')
                self.assertEqual(p['schema'],'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1')
                self.assertEqual(r['schema'],'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1')
                self.assertEqual({x.name for x in output.iterdir()},{'started.json','observation_payload.json','receipt.json'})
                for doc in (p,r):
                    self.assertTrue(all(doc[key] is False for key in writer.FLAGS))
                    self.assertFalse(doc['external_unregistered_attempt_discovery_performed'])
                    for path in current.values():self.assertNotIn(str(path),doc['source_hashes'])
                    for source,sha in doc['source_hashes'].items():self.assertEqual(writer.sha(Path(source).read_bytes()),sha)
                # Avoid contaminating the subsequent chain's semantic local scanner with an un-read writer attempt.
                # A successful write is intentionally not yet a resolved observation until its reader exists.
                if name=='v3':
                    for x in output.iterdir():x.unlink()
                    output.rmdir()

    def test_no_new_and_live_source_claim_reject_before_output_or_live_read(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_observation_rejections_') as folder:
            root=Path(folder);research=root/'research';research.mkdir();parent=deepcopy(oldwriter.PARENT_BOUND)
            capture,current=capture_chain(root,research,parent,None,'no_new_capture')
            args,value=registration(root,research,parent,capture,'no_new_writer')
            with patch.multiple(writer,RESEARCH=research,CURRENT=current),self.assertRaises(ValueError):writer.run(**args)
            self.assertFalse(Path(value['output_directory']).exists())
            live=current['QQQ'];auditpath=Path(capture['readback_reference']['path']);audit=writer.decode(auditpath.read_bytes())
            audit['source_hashes'][str(live)]=writer.sha(live.read_bytes());auditpath.write_bytes(writer.encode(audit))
            forged=deepcopy(capture);forged['readback_reference']['sha256']=writer.sha(auditpath.read_bytes())
            args,value=registration(root,research,parent,forged,'forged_live_writer');real_read=Path.read_bytes
            def no_live(path):
                if path==live:raise AssertionError('Live claim read before rejection')
                return real_read(path)
            with (patch.multiple(writer,RESEARCH=research,CURRENT=current),patch.object(Path,'read_bytes',no_live),self.assertRaises(ValueError)):
                writer.run(**args)
            self.assertFalse(Path(value['output_directory']).exists())

    def test_partial_external_start_association_namespace_resource_clock_and_failure(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_observation_attempt_attack_') as folder:
            root=Path(folder);research=root/'research';research.mkdir();parent=parents.compact_parent(root,research)
            capture,current=capture_chain(root,research,parent,'2026-10-09','candidate_capture')
            with patch.multiple(writer,RESEARCH=research,CURRENT=current):
                def invoke(name,check='2026-10-12T13:30:00+00:00',start='2026-10-09T20:02:00+00:00'):
                    args,value=registration(root,research,parent,capture,name)
                    with patch.object(writer,'now',side_effect=clock(start,check)):return writer.run(**args),value
                partial=research/'renamed_unknown_attempt';partial.mkdir();(partial/'started.json').write_bytes(writer.encode(dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V4')))
                try:
                    with self.assertRaisesRegex(ValueError,'UNRESOLVED_PRIOR'):invoke('rejected_partial')
                    self.assertFalse((research/'rejected_partial').exists())
                finally:(partial/'started.json').unlink();partial.rmdir()
                # The V4 parent's most recent observation is external to research and its START is inherited by hash.
                h=writer.decode(Path(parent['reference']['path']).read_bytes())['history'];external=Path(h['observations'][-1]['payload_reference']['path']).parent
                externalstart=external/'started.json';old=externalstart.read_bytes();externalstart.write_bytes(old+b' ')
                try:
                    with self.assertRaises(ValueError):invoke('rejected_external_start')
                    self.assertFalse((research/'rejected_external_start').exists())
                finally:externalstart.write_bytes(old)
                extra=external/'unbound_side_file';extra.write_bytes(b'unknown')
                try:
                    with self.assertRaises(ValueError):invoke('rejected_external_inventory')
                    self.assertFalse((research/'rejected_external_inventory').exists())
                finally:extra.unlink()
                with patch.object(writer.shutil,'disk_usage',return_value=SimpleNamespace(free=0)),self.assertRaisesRegex(ValueError,'Resource stop'):
                    invoke('rejected_resource')
                self.assertFalse((research/'rejected_resource').exists())
                # Failure must remain on disk; the semantic scanner blocks a different retry namespace.
                with self.assertRaisesRegex(ValueError,'clock reversal'):invoke('failed_clock',check='2026-10-09T20:00:00+00:00')
                self.assertTrue((research/'failed_clock'/'failure.json').is_file())
                self.assertTrue((research/'failed_clock'/'observation_payload.json').is_file())
                with self.assertRaisesRegex(ValueError,'UNRESOLVED_PRIOR'):invoke('renamed_clock_retry')
                self.assertFalse((research/'renamed_clock_retry').exists())

    def test_durable_receipt_failure_and_own_started_drift_preserve_attempt(self):
        for mode in ('receipt_failure','own_started_drift'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_observation_durable_') as folder:
                root=Path(folder);research=root/'research';research.mkdir();parent=deepcopy(oldwriter.PARENT_BOUND)
                capture,current=capture_chain(root,research,parent,'2026-10-08','candidate_capture')
                args,value=registration(root,research,parent,capture,'failed_attempt');real_save=writer.save
                def altered_save(path,value):
                    if mode=='receipt_failure' and path.name=='receipt.json':raise ValueError('Injected receipt durability failure')
                    result=real_save(path,value)
                    if mode=='own_started_drift' and path.name=='started.json':path.write_bytes(path.read_bytes()+b' ')
                    return result
                with (patch.multiple(writer,RESEARCH=research,CURRENT=current),patch.object(writer,'save',side_effect=altered_save),
                      patch.object(writer,'now',side_effect=clock('2026-10-09T20:02:00+00:00','2026-10-09T20:03:00+00:00')),
                      self.assertRaises(ValueError)):
                    writer.run(**args)
                output=Path(value['output_directory']);failure=writer.decode((output/'failure.json').read_bytes())
                self.assertTrue((output/'started.json').is_file());self.assertTrue((output/'observation_payload.json').is_file())
                self.assertTrue(failure['observation_payload_must_not_be_discarded'])
                self.assertTrue(all(failure[key] is False for key in writer.FLAGS))
                retry,_=registration(root,research,parent,capture,'renamed_retry')
                with patch.multiple(writer,RESEARCH=research,CURRENT=current),self.assertRaisesRegex(ValueError,'UNRESOLVED_PRIOR'):
                    writer.run(**retry)
                self.assertFalse((research/'renamed_retry').exists())


if __name__=='__main__':unittest.main()
