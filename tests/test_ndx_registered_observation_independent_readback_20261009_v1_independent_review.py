"""Adversarial registered observer readback in full physical temp chains."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_registered_observation_independent_readback_20261009_v1 as reader
from scripts import ndx_registered_observation_writer_20261009_v1 as writer
from scripts import ndx_prospective_observation_writer_v3_20261009 as oldwriter
import test_ndx_registered_observation_independent_readback_20261009_v1 as author


def resign(args,output,mutate):
    docs={name:reader.decode((output/name).read_bytes())for name in ('started.json','observation_payload.json','receipt.json')}
    mutate(docs)
    for name in ('started.json','observation_payload.json'):(output/name).write_bytes(reader.enc(docs[name]))
    args['payload_reference']['sha256']=reader.sha((output/'observation_payload.json').read_bytes())
    docs['receipt.json']['payload_reference']=deepcopy(args['payload_reference'])
    (output/'receipt.json').write_bytes(reader.enc(docs['receipt.json']))
    args['receipt_reference']['sha256']=reader.sha((output/'receipt.json').read_bytes())


class IndependentRegisteredObservationReadbackTests(unittest.TestCase):
    def test_host_pending_all_configuration_before_io(self):
        for mode in ('registration','registration_core','reference_core',*reader.DEPENDENCIES):
            deps=deepcopy(reader.DEPENDENCIES)
            if mode in deps:deps[mode]=(deps[mode][0],None)
            with (self.subTest(mode=mode),patch.multiple(reader,WRITER_SHA=writer.LOADED_SHA,DEPENDENCIES=deps,
                REGISTRATION_CORE=(reader.REGISTRATION_CORE[0],None if mode=='registration_core' else reader.REGISTRATION_CORE[1]),
                REFERENCE_CORE=(reader.REFERENCE_CORE[0],None if mode=='reference_core' else reader.REFERENCE_CORE[1])),
                patch.object(Path,'read_bytes',side_effect=AssertionError('Source IO before pending host anchor'))):
                with self.assertRaises(ValueError):reader.readback(registration_path='E:/synthetic_registration.json',
                    registration_sha256=None if mode=='registration' else 'a'*64,
                    payload_reference=dict(path='E:/p.json',sha256='b'*64),receipt_reference=dict(path='E:/r.json',sha256='c'*64),execute=True)

    def test_resigned_full_nested_shape_and_metadata_authority_reject(self):
        attacks={
            'nested_extra':lambda docs:docs['observation_payload.json']['full_original_sources_preserved']['QQQ'].update(extra_authority=True),
            'actual_schema':lambda docs:[d.update(actual_parent_schema='PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V4')for d in docs.values()],
            'external_discovery':lambda docs:[d.update(external_unregistered_attempt_discovery_performed=True)for d in docs.values()],
            'csv_pointer':lambda docs:docs['observation_payload.json']['source_row_locations']['SPY'].update(original_data_row_index=0),
            'late_upgrade':lambda docs:docs['receipt.json'].update(timing_classification='WITHIN_CONSERVATIVE_OBSERVATION_WINDOW'),
        }
        for name,mutate in attacks.items():
            with self.subTest(attack=name),tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_observer_forged_')as folder:
                root=Path(folder);research=root/'research';research.mkdir()
                args,current,output=author.publish(root,research,deepcopy(oldwriter.PARENT_BOUND),'2026-10-08')
                resign(args,output,mutate)
                with patch.multiple(reader,RESEARCH=research,CURRENT=current,WRITER_SHA=writer.LOADED_SHA),self.assertRaises(ValueError):reader.readback(**args)
                self.assertTrue((output/'failure.json').is_file());self.assertTrue((output/'observation_payload.json').is_file())
                self.assertFalse((output/'independent_readback.json').exists())

    def test_resigned_source_closure_lie_rejects_without_live_read(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_observer_closure_')as folder:
            root=Path(folder);research=root/'research';research.mkdir()
            args,current,output=author.publish(root,research,deepcopy(oldwriter.PARENT_BOUND),'2026-10-08')
            live=current['QQQ'];digest=reader.sha(live.read_bytes())
            resign(args,output,lambda docs:[d['source_hashes'].update({str(live):digest})for d in docs.values()])
            original=Path.read_bytes
            def forbidden(path):
                if path==live:raise AssertionError('Forged payload source claim triggered live read')
                return original(path)
            with (patch.multiple(reader,RESEARCH=research,CURRENT=current,WRITER_SHA=writer.LOADED_SHA),patch.object(Path,'read_bytes',forbidden),
                  self.assertRaisesRegex(ValueError,'Whole producer source closure')):reader.readback(**args)
            self.assertTrue((output/'failure.json').exists())

    def test_physical_post_inspect_drift_resource_and_report_failure_preserve(self):
        for mode in ('source_drift','started_drift','resource','report_failure'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_observer_finalguard_')as folder:
                root=Path(folder);research=root/'research';research.mkdir()
                args,current,output=author.publish(root,research,deepcopy(oldwriter.PARENT_BOUND),'2026-10-08')
                original=reader.inspect;save=reader.save;changed={}
                def inspect(*pos,**kw):
                    result=original(*pos,**kw)
                    path=output/'started.json'if mode=='started_drift'else Path(output.parent/'observation_capture'/'QQQ.csv')
                    changed['path']=path;changed['raw']=path.read_bytes();path.write_bytes(changed['raw']+b' ');return result
                def fail_report(path,value):
                    if path.name=='independent_readback.json':raise ValueError('Injected durable readback failure')
                    return save(path,value)
                with patch.multiple(reader,RESEARCH=research,CURRENT=current,WRITER_SHA=writer.LOADED_SHA):
                    try:
                        if mode in ('source_drift','started_drift'):
                            with patch.object(reader,'inspect',side_effect=inspect),self.assertRaises(ValueError):reader.readback(**args)
                        elif mode=='resource':
                            with patch.object(reader.shutil,'disk_usage',return_value=SimpleNamespace(free=0)),self.assertRaisesRegex(ValueError,'Resource stop'):reader.readback(**args)
                        else:
                            with patch.object(reader,'save',side_effect=fail_report),self.assertRaisesRegex(ValueError,'Injected durable'):reader.readback(**args)
                    finally:
                        if changed:changed['path'].write_bytes(changed['raw'])
                    self.assertTrue((output/'started.json').is_file());self.assertTrue((output/'observation_payload.json').is_file());self.assertTrue((output/'receipt.json').is_file())
                    self.assertTrue((output/'failure.json').is_file());self.assertFalse((output/'independent_readback.json').exists())
                    with self.assertRaises(ValueError):reader.readback(**args)


if __name__=='__main__':unittest.main()
