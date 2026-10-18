"""Independent full physical capture readback tests, temporary artifacts only."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_registered_forward_capture_runtime_20261009_v1 as producer
from scripts import ndx_registered_forward_capture_independent_readback_20261009_v1 as reader
from scripts import ndx_prospective_observation_writer_v3_20261009 as writer
import test_ndx_registered_forward_capture_runtime_20261009_v1_independent_review as physical

PRODUCER_SHA='e7850782dcc4c230353281935ebc428a7c02349a00cea89731ed16ea27e49190'


def publish(root,research,parent,session,name):
    current=physical.current_files(root,parent,session)
    path,digest,value=physical.registered(root,research,parent,name)
    with (patch.multiple(producer,RESEARCH=research,CURRENT=current),patch.object(producer,'now',
        side_effect=['2026-10-09T20:01:00+00:00','2026-10-09T20:01:01+00:00'])):
        result=producer.run(registration_path=str(path),registration_sha256=digest,execute=True)
    return dict(registration_path=str(path),registration_sha256=digest,**result,execute=True),current,value


class IndependentRegisteredCaptureReadbackTests(unittest.TestCase):
    def test_pending_and_host_references_pre_io(self):
        for mode in ('producer','registration','registration_core','reference_core','dependency','capture','publication'):
            deps=deepcopy(reader.DEPENDENCIES)
            if mode=='dependency':deps['capture_core']=(deps['capture_core'][0],None)
            args=dict(registration_path='E:/synthetic_registration.json',registration_sha256='a'*64,
                capture_reference=dict(path='E:/synthetic/capture.json',sha256='b'*64),
                publication_reference=dict(path='E:/synthetic/publication.json',sha256='c'*64),
                output_directory='E:/synthetic_readback',execute=True)
            if mode=='registration':args['registration_sha256']=None
            if mode in ('capture','publication'):args[mode+'_reference']['sha256']=None
            with (self.subTest(mode=mode),patch.multiple(reader,PRODUCER_SHA=None if mode=='producer' else PRODUCER_SHA,DEPENDENCIES=deps,
                REGISTRATION_CORE=(reader.REGISTRATION_CORE[0],None if mode=='registration_core' else reader.REGISTRATION_CORE[1]),
                REFERENCE_CORE=(reader.REFERENCE_CORE[0],None if mode=='reference_core' else reader.REFERENCE_CORE[1])),
                patch.object(Path,'read_bytes',side_effect=AssertionError('IO before pending pin'))):
                with self.assertRaises(ValueError):reader.readback(**args)

    def test_full_physical_v3_zero_one_v4_one_without_live_reads_or_capture_kernel(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_registered_capture_reader_') as folder:
            root=Path(folder);research=root/'research';research.mkdir()
            cases=[('v3_zero',deepcopy(writer.PARENT_BOUND),None,69,'NO_NEW_SESSION'),
                ('v3_one',deepcopy(writer.PARENT_BOUND),'2026-10-08',69,'ONE_NEW_SESSION_CAPTURE_CANDIDATE'),
                ('v4_one',physical.compact_parent(root,research),'2026-10-09',70,'ONE_NEW_SESSION_CAPTURE_CANDIDATE')]
            for name,parent,session,count,status in cases:
                args,current,value=publish(root,research,parent,session,name)
                for path in current.values():path.write_bytes(b'cache changed after publication')
                real_read=Path.read_bytes;real_private=reader.private_module;compiled=[]
                def forbid_live(path):
                    if path in current.values():raise AssertionError('Reader attempted current cache IO')
                    return real_read(path)
                def private(path,*pos,**kw):
                    compiled.append(Path(path));module=real_private(path,*pos,**kw)
                    if Path(path)==reader.ROOT/reader.DEPENDENCIES['parent_view'][0]:
                        module.append_observation_history_v4=lambda **kw:(_ for _ in ()).throw(AssertionError('Append called'))
                    return module
                output=research/(name+'_independent')
                with (patch.multiple(reader,RESEARCH=research,CURRENT=current,PRODUCER_SHA=PRODUCER_SHA),
                      patch.object(Path,'read_bytes',forbid_live),patch.object(reader,'private_module',side_effect=private),
                      patch.dict('sys.modules',{'backtest.ndx_forward_parent_capture_research_v4':SimpleNamespace(),
                          'backtest.ndx_prospective_observation_parent_history_research_v4':SimpleNamespace()})):
                    report=reader.readback(**args,output_directory=str(output))
                    with self.assertRaisesRegex(ValueError,'create-only'):reader.readback(**args,output_directory=str(output))
                audit=reader.decode(Path(report['path']).read_bytes())
                self.assertEqual(audit['status'],'PURE_FORWARD_CAPTURE_READBACK_PASS')
                self.assertEqual((audit['counts']['parent_typed_row_count'],audit['counts']['status']),(count,status))
                self.assertTrue(all(audit[key] is False for key in reader.FALSE_FIELDS))
                self.assertFalse(audit['capture_core_called']);self.assertFalse(audit['current_live_cache_read_or_reverified'])
                self.assertNotIn(reader.ROOT/reader.DEPENDENCIES['capture_core'][0],compiled)
                self.assertEqual({p.name for p in output.iterdir()},{'started.json','independent_readback.json'})
                for path in current.values():self.assertNotIn(str(path),audit['source_hashes'])
                for source,sha in audit['source_hashes'].items():self.assertEqual(reader.sha(Path(source).read_bytes()),sha)

    def test_full_physical_forgeries_namespace_resource_source_drift_and_failure_retention(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_registered_capture_attack_') as folder:
            root=Path(folder);research=root/'research';research.mkdir()
            args,current,value=publish(root,research,deepcopy(writer.PARENT_BOUND),'2026-10-08','captured_source')
            with patch.multiple(reader,RESEARCH=research,CURRENT=current,PRODUCER_SHA=PRODUCER_SHA):
                cp=Path(args['capture_reference']['path']);pp=Path(args['publication_reference']['path']);oldc,oldp=cp.read_bytes(),pp.read_bytes()
                for name,mutate in (
                    ('noncount',lambda d:d['plan']['source_evidence']['QQQ']['included_original_row_indexes'].pop()),
                    ('authority',lambda d:d.update(source_authenticity_verified=True)),
                    ('closure',lambda d:d['source_hashes'].update({'E:/synthetic_forged_source':'f'*64}))):
                    document=reader.decode(oldc);mutate(document);cp.write_bytes(reader.encode(document))
                    cref=reader.reference(str(cp),reader.sha(cp.read_bytes()));publication=reader.decode(oldp);publication['capture_reference']=cref
                    pp.write_bytes(reader.encode(publication));output=research/('rejected_'+name)
                    with self.assertRaises(ValueError):reader.readback(**dict(args,capture_reference=cref,
                        publication_reference=reader.reference(str(pp),reader.sha(pp.read_bytes()))),output_directory=str(output))
                    self.assertFalse(output.exists());cp.write_bytes(oldc);pp.write_bytes(oldp)
                extra=cp.parent/'unknown'
                for kind in ('file','directory','link'):
                    output=research/('rejected_inventory_'+kind)
                    if kind=='file':extra.write_bytes(b'unknown')
                    elif kind=='directory':extra.mkdir()
                    else:extra.symlink_to(cp)
                    try:
                        with self.assertRaises(ValueError):reader.readback(**args,output_directory=str(output))
                        self.assertFalse(output.exists())
                    finally:
                        if kind=='directory':extra.rmdir()
                        else:extra.unlink()
                output=research/'rejected_resource'
                with patch.object(reader.shutil,'disk_usage',return_value=SimpleNamespace(free=0)),self.assertRaisesRegex(ValueError,'Resource stop before namespace'):
                    reader.readback(**args,output_directory=str(output))
                self.assertFalse(output.exists())
                real_formula=reader.reconstruct_plan;snapshot=cp.parent/'QQQ.csv';old=snapshot.read_bytes()
                def drift(**kw):
                    result=real_formula(**kw);snapshot.write_bytes(old+b'drift');return result
                try:
                    with patch.object(reader,'reconstruct_plan',side_effect=drift),self.assertRaises(ValueError):
                        reader.readback(**args,output_directory=str(research/'rejected_source_drift'))
                    self.assertFalse((research/'rejected_source_drift').exists())
                finally:snapshot.write_bytes(old)
                real_save=reader.save
                def fail_report(path,value):
                    if path.name=='independent_readback.json':raise ValueError('Injected report write')
                    return real_save(path,value)
                output=research/'failed_report'
                with patch.object(reader,'save',side_effect=fail_report),self.assertRaisesRegex(ValueError,'Injected report'):
                    reader.readback(**args,output_directory=str(output))
                self.assertEqual({p.name for p in output.iterdir()},{'started.json','failure.json'})
                self.assertTrue(all(reader.decode((output/'failure.json').read_bytes())[key] is False for key in reader.FALSE_FIELDS))
                with self.assertRaisesRegex(ValueError,'create-only'):reader.readback(**args,output_directory=str(output))
                def drift_start(path,value):
                    result=real_save(path,value)
                    if path.name=='started.json':path.write_bytes(path.read_bytes()+b' ')
                    return result
                with patch.object(reader,'save',side_effect=drift_start),self.assertRaises(ValueError):
                    reader.readback(**args,output_directory=str(research/'failed_own_start_drift'))


if __name__=='__main__':unittest.main()
