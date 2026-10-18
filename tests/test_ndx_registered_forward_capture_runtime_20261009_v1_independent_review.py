"""Registered V3/V4 capture attacks using only disposable source/output paths."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_registered_forward_capture_runtime_20261009_v1 as capture
from scripts import ndx_registered_compact_history_runtime_20261009_v1 as compact
from scripts import ndx_registered_compact_history_independent_readback_20261009_v1 as readback
from scripts import ndx_prospective_observation_writer_v3_20261009 as writer
from backtest import ndx_forward_capture_runtime_registration_research_v1 as registration_core
import test_ndx_registered_compact_history_runtime_20261009_v1_independent_review as physical

REGISTRATION_SHA='e04169b111d2788e3dadba657a6c4823d2b0665de17a81e0c84bb9169990abde'


def registered(root,research,parent,name):
    value=dict(schema=registration_core.SCHEMA,runtime_reference=capture.reference(str(capture.SOURCE),capture.LOADED_SHA),
        dependency_references=capture.configured(capture.DEPENDENCIES),parent=deepcopy(parent),
        output_directory=str(research/name),**registration_core.FLAGS)
    path=root/(name+'_registration.json');path.write_bytes(capture.encode(value))
    return path,capture.digest(path.read_bytes()),value


def current_files(root,parent,session=None):
    h=capture.decode(Path(parent['reference']['path']).read_bytes())['history']
    refs=h.get('accounted_baseline_references',h.get('captured_source_references'))
    folder=root/('current_'+(session or 'none'));folder.mkdir()
    paths={}
    for ticker in ('QQQ','SPY'):
        raw=Path(refs[ticker]['path']).read_bytes()
        if session:raw+=(session+',100,110,90,100,1000\n').encode()
        paths[ticker]=folder/(ticker+'.csv');paths[ticker].write_bytes(raw)
    return paths


def compact_parent(root,research):
    observation=physical.physical_observation(root)
    path,digest,value=physical.registration(root,research,observation)
    with patch.object(compact,'RESEARCH',research):published=compact.run(registration_path=str(path),registration_sha256=digest,execute=True)
    with patch.object(readback,'RESEARCH',research):audit=readback.readback(registration_path=str(path),registration_sha256=digest,
        history_reference=published['history_reference'],publication_reference=published['publication_reference'],
        output_directory=str(research/'compact_independent'),execute=True)
    return dict(reference=published['history_reference'],publication_reference=published['publication_reference'],
        readback_reference=audit,reader_reference=capture.reference(str(readback.SOURCE),readback.LOADED_SHA))


class IndependentRegisteredCaptureTests(unittest.TestCase):
    def test_pending_pins_pre_io(self):
        for mode in ('registration_core','reference_core','dependency','registration'):
            deps=deepcopy(capture.DEPENDENCIES)
            if mode=='dependency':deps['capture_core']=(deps['capture_core'][0],None)
            with (self.subTest(mode=mode),patch.multiple(capture,DEPENDENCIES=deps,
                REGISTRATION_CORE=(capture.REGISTRATION_CORE[0],None if mode=='registration_core' else REGISTRATION_SHA),
                REFERENCE_CORE=(capture.REFERENCE_CORE[0],None if mode=='reference_core' else capture.REFERENCE_CORE[1])),
                patch.object(Path,'read_bytes',side_effect=AssertionError('IO before valid pin'))):
                with self.assertRaises(ValueError):capture.run(registration_path='E:/synthetic_registration.json',
                    registration_sha256=None if mode=='registration' else 'a'*64,execute=True)

    def test_full_physical_v3_zero_one_clock_and_live_interval_only(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_registered_capture_v3_') as folder:
            root=Path(folder);research=root/'research';research.mkdir();parent=deepcopy(writer.PARENT_BOUND)
            for session,status in ((None,'NO_NEW_SESSION'),('2026-10-08','ONE_NEW_SESSION_CAPTURE_CANDIDATE')):
                current=current_files(root,parent,session);path,digest,value=registered(root,research,parent,'capture_'+('zero' if session is None else 'one'))
                with (patch.multiple(capture,RESEARCH=research,CURRENT=current,REGISTRATION_CORE=(capture.REGISTRATION_CORE[0],REGISTRATION_SHA)),
                    patch.object(capture,'now',side_effect=['2026-10-08T20:01:00+00:00','2026-10-08T20:01:01+00:00']),
                    patch.dict('sys.modules',{'backtest.ndx_prospective_observation_parent_history_research_v4':SimpleNamespace(),
                        'backtest.ndx_forward_source_capture_scoped_research':SimpleNamespace(),
                        'backtest.ndx_forward_source_capture_research':SimpleNamespace()})):
                    result=capture.run(registration_path=str(path),registration_sha256=digest,execute=True)
                    with self.assertRaisesRegex(ValueError,'Create-only'):capture.run(registration_path=str(path),registration_sha256=digest,execute=True)
                document=capture.decode(Path(result['capture_reference']['path']).read_bytes())
                self.assertEqual(document['plan']['status'],status)
                self.assertEqual(len(document['plan']['known_typed_rows']),69)
                self.assertEqual(document['capture_started_at'],'2026-10-08T20:01:00+00:00')
                self.assertTrue(all(document[key] is False for key in capture.FLAGS))
                self.assertEqual({p.name for p in Path(value['output_directory']).iterdir()},
                    {'started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'})
                for live in current.values():self.assertNotIn(str(live),document['source_hashes'])
                for source,claim in document['source_hashes'].items():self.assertEqual(capture.digest(Path(source).read_bytes()),claim)
                # Later mutablecache changes cannot invalidate saved closure; they have no permanent source role.
                for live in current.values():live.write_bytes(b'changed after capture')
                for source,claim in document['source_hashes'].items():self.assertEqual(capture.digest(Path(source).read_bytes()),claim)

    def test_full_physical_v4_parent_candidate_host_inventory_resource_and_failure(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_registered_capture_v4_') as folder:
            root=Path(folder);research=root/'research';research.mkdir();parent=compact_parent(root,research)
            current=current_files(root,parent,'2026-10-09')
            with patch.multiple(capture,RESEARCH=research,CURRENT=current,REGISTRATION_CORE=(capture.REGISTRATION_CORE[0],REGISTRATION_SHA)):
                def invoke(name,clock=('2026-10-09T20:01:00+00:00','2026-10-09T20:01:01+00:00')):
                    path,digest,value=registered(root,research,parent,name)
                    with patch.object(capture,'now',side_effect=clock):return capture.run(registration_path=str(path),registration_sha256=digest,execute=True),value
                result,value=invoke('v4_candidate')
                document=capture.decode(Path(result['capture_reference']['path']).read_bytes())
                self.assertEqual(document['plan']['status'],'ONE_NEW_SESSION_CAPTURE_CANDIDATE')
                self.assertEqual(len(document['plan']['known_typed_rows']),70)
                self.assertEqual(document['plan']['candidate_session'],'2026-10-09')
                parentfolder=Path(parent['reference']['path']).parent;extra=parentfolder/'unexpected'
                extra.mkdir()
                try:
                    with self.assertRaises((ValueError,OSError)):invoke('rejected_inventory')
                    self.assertFalse((research/'rejected_inventory').exists())
                finally:extra.rmdir()
                target=root/'unrelated_secret';target.write_bytes(b'must not read linked inventory')
                extra.symlink_to(target);read_bytes=Path.read_bytes
                def prevent_link_read(path):
                    if path==extra:raise AssertionError('Linked inventory read before safe validation')
                    return read_bytes(path)
                try:
                    with patch.object(Path,'read_bytes',prevent_link_read),self.assertRaises(ValueError):invoke('rejected_link_inventory')
                    self.assertFalse((research/'rejected_link_inventory').exists())
                finally:extra.unlink()
                with patch.object(capture.shutil,'disk_usage',return_value=SimpleNamespace(free=0)),self.assertRaisesRegex(ValueError,'RESOURCE_STOP'):
                    invoke('rejected_resource')
                self.assertFalse((research/'rejected_resource').exists())
                path,digest,bad=registered(root,research,parent,'rejected_host')
                bad['dependency_references']['capture_core']['sha256']='f'*64;path.write_bytes(capture.encode(bad))
                with self.assertRaisesRegex(ValueError,'Host dependency'):capture.run(registration_path=str(path),registration_sha256=capture.digest(path.read_bytes()),execute=True)
                self.assertFalse((research/'rejected_host').exists())
                with self.assertRaises(ValueError):invoke('rejected_clock',('2026-10-09T20:02:00+00:00','2026-10-09T20:01:00+00:00'))
                self.assertTrue((research/'rejected_clock'/'failure.json').is_file())
                started=parentfolder/'started.json';original_start=started.read_bytes();clock_calls=[]
                def drift_parent_start():
                    clock_calls.append(1)
                    if len(clock_calls)==1:started.write_bytes(original_start+b' ')
                    return '2026-10-09T20:01:00+00:00'
                path,digest,value=registered(root,research,parent,'rejected_parent_start_drift')
                try:
                    with patch.object(capture,'now',side_effect=drift_parent_start),self.assertRaisesRegex(ValueError,'Source SHA changed'):
                        capture.run(registration_path=str(path),registration_sha256=digest,execute=True)
                finally:started.write_bytes(original_start)
                self.assertTrue((research/'rejected_parent_start_drift'/'failure.json').is_file())
                real_read=capture.read_current
                def drift(path):
                    raw=real_read(path)
                    if path==current['SPY']:path.write_bytes(raw+b'drift')
                    return raw
                old=current['SPY'].read_bytes()
                try:
                    with patch.object(capture,'read_current',side_effect=drift),self.assertRaisesRegex(ValueError,'SHA changed'):invoke('rejected_live_drift')
                finally:current['SPY'].write_bytes(old)
                failed=research/'rejected_save';real_save=capture.save
                def fail_capture(path,value):
                    if path.name=='capture.json':raise ValueError('Injected capture save')
                    return real_save(path,value)
                with patch.object(capture,'save',side_effect=fail_capture),self.assertRaisesRegex(ValueError,'Injected capture'):invoke('rejected_save')
                self.assertTrue((failed/'started.json').is_file());self.assertTrue((failed/'failure.json').is_file())
                self.assertFalse((failed/'publication.json').exists())
                with self.assertRaisesRegex(ValueError,'Create-only'):invoke('rejected_save')
                def drift_own_start(path,value):
                    result=real_save(path,value)
                    if path.name=='started.json':path.write_bytes(path.read_bytes()+b' ')
                    return result
                with patch.object(capture,'save',side_effect=drift_own_start),self.assertRaisesRegex(ValueError,'Source SHA changed'):
                    invoke('rejected_own_start_drift')


if __name__=='__main__':unittest.main()
