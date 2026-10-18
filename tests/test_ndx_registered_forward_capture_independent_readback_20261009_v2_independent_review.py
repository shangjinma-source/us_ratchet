"""Independent V5 readback attacks; only temporary physical artifact chains."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as reader
from scripts import ndx_registered_forward_capture_runtime_20261009_v2 as producer
import test_ndx_registered_forward_capture_runtime_20261009_v2_independent_review as physical
from ndx_v5_physical_parent_fixture import physical_gap_parent,envelope,reference
from test_ndx_registered_forward_capture_independent_readback_20261009_v2 import checkers


def published(root,research,parent,name='capture'):
    current=physical.current_files(root,parent,name);captured,_=physical.run(root,research,parent,name,current)
    args,_=physical.registered(root,research,parent,name)
    return dict(**args,**captured),current


def readback(args,current,research,name='independent'):
    with patch.multiple(reader,RESEARCH=research,CURRENT=current,PRODUCER_SHA=producer.LOADED_SHA):
        return reader.readback(**args,output_directory=str(research/name))


class IndependentReadbackV2Tests(unittest.TestCase):
    def test_complete_physical_v5_no_kernel_execution_no_live_read_and_failure_guards(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_V5_INDEPENDENT_READER_')as folder:
            root=Path(folder);research=root/'research';research.mkdir();parent,_=physical_gap_parent(root,research)
            args,current=published(root,research,parent)
            for path in current.values():path.write_bytes(b'changed mutable bytes')
            original_read=Path.read_bytes;original_private=reader.private_module
            def no_live(path):
                if path in current.values():raise AssertionError('Reader live cache read')
                return original_read(path)
            def private(path,raw,digest,replacements=()):
                if Path(path)in (reader.PRODUCER,reader.ROOT/reader.DEPENDENCIES['capture_core'][0],reader.GAP_CORE[0]):
                    raise AssertionError('Producer, current capture or gap append executed')
                module=original_private(path,raw,digest,replacements)
                if hasattr(module,'append_observation_history_v4'):
                    module.append_observation_history_v4=lambda **kwargs:(_ for _ in()).throw(AssertionError('Actual append called'))
                return module
            with patch.object(Path,'read_bytes',no_live),patch.object(reader,'private_module',side_effect=private),patch.object(producer,'run',side_effect=AssertionError('Producer called')):
                report=readback(args,current,research)
            audit=reader.decode(Path(report['path']).read_bytes())
            self.assertEqual((audit['counts']['parent_typed_row_count'],audit['counts']['parent_actual_observation_count'],audit['counts']['parent_gap_count']),(71,2,9))
            self.assertEqual(audit['counts']['status'],'BLOCKED_SOURCE_DIAGNOSTICS')
            self.assertEqual(audit['actual_parent_schema'],'PROSPECTIVE_GAP_EXTENSION_HISTORY_V5')
            self.assertTrue(all(audit[k]is False for k in reader.FALSE_FIELDS))
            self.assertFalse(audit['gap_core_called']);self.assertFalse(audit['producer_called'])
            for path,digest in audit['source_hashes'].items():self.assertEqual(reference(path)['sha256'],digest)
            self.assertEqual({p.name for p in (research/'independent').iterdir()},{'started.json','independent_readback.json'})
            with self.assertRaisesRegex(ValueError,'create-only'):readback(args,current,research)
            original_save=reader.save
            def drift_own_started(path,value):
                result=original_save(path,value)
                if path.name=='started.json':path.write_bytes(path.read_bytes()+b' ')
                return result
            with patch.object(reader,'save',side_effect=drift_own_started),self.assertRaises(ValueError):
                readback(args,current,research,'failed_own_start')
            failure=reader.decode((research/'failed_own_start'/'failure.json').read_bytes())
            self.assertTrue(all(failure[k]is False for k in reader.FALSE_FIELDS))
            self.assertTrue((research/'failed_own_start'/'started.json').is_file())
            # Original capture audit START is an observed immutable source even though
            # it is not an external source-authentication anchor.
            old_start=Path(envelope(parent)['document']['history']['capture_references']['readback_reference']['path']).parent/'started.json'
            before=old_start.read_bytes()
            def drift_upstream_after_report(path,value):
                result=original_save(path,value)
                if path.name=='independent_readback.json':old_start.write_bytes(before+b' ')
                return result
            try:
                with patch.object(reader,'save',side_effect=drift_upstream_after_report),self.assertRaises(ValueError):
                    readback(args,current,research,'failed_upstream_start')
                self.assertTrue((research/'failed_upstream_start'/'failure.json').is_file())
            finally:old_start.write_bytes(before)

    def test_coordinated_original_metadata_and_prior_evidence_rejected_by_independent_guard(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_V5_READER_ORIGINAL_ATTACK_')as folder:
            root=Path(folder);research=root/'research';research.mkdir();parent,_=physical_gap_parent(root,research)
            h=envelope(parent)['document']['history'];refs=h['capture_references'];artifact=Path(h['accounted_prefix_evidence_references']['QQQ']['path'])
            paths=[Path(parent[k]['path'])for k in ('reference','publication_reference','readback_reference')]+[Path(refs[k]['path'])for k in ('reference','publication_reference','readback_reference')]
            paths+=[Path(parent['reference']['path']).parent/'started.json',artifact]
            before={path:path.read_bytes()for path in paths};checker,csv=checkers()
            raw={key:(reader.ROOT/path).read_bytes()for key,(path,_)in reader.DEPENDENCIES.items()}
            prefix=reader.private_prefix_checker(raw,{})
            for mode in ('external_clock','quote_type','extra','evidence','prior_source'):
                try:
                    if mode in ('external_clock','quote_type','extra'):
                        key,value={'external_clock':('external_clock_attestation_verified',True),'quote_type':('quote_source_type','NETWORK_QUOTE_VERIFIED'),'extra':('extra_authority',True)}[mode]
                        forged=physical.resign_upstream_capture_metadata(parent,key,value)
                    elif mode=='evidence':forged=physical.resign_parent(parent,artifact,b'{"forged":true}\n')
                    else:
                        def mutate(history):
                            item=history['full_capture_source_references']['QQQ'];history['prior_state_preserved']['source_hashes'][item['path']]=item['sha256']
                        forged=physical.resign_parent(parent,artifact,artifact.read_bytes(),mutate)
                    physical.view.inspect_parent_history_v5(envelope(forged))
                    with self.subTest(mode=mode),self.assertRaises(ValueError):reader.verify_parent_chain(envelope(forged),checker,prefix,csv,{})
                finally:
                    for path,data in before.items():path.write_bytes(data)

    def test_all_host_pins_are_validated_before_any_source_read(self):
        for role in ('PRODUCER_SHA','REGISTRATION_CORE','REFERENCE_CORE','PREFIX_CORE','GAP_CORE','CSV_READER',*reader.DEPENDENCIES):
            deps=deepcopy(reader.DEPENDENCIES);patches=dict(PRODUCER_SHA=producer.LOADED_SHA,DEPENDENCIES=deps)
            if role in deps:deps[role]=(deps[role][0],None)
            elif role=='PRODUCER_SHA':patches[role]=None
            else:patches[role]=(getattr(reader,role)[0],None)
            with (self.subTest(role=role),patch.multiple(reader,**patches),
                patch.object(Path,'read_bytes',side_effect=AssertionError('Pending pin source IO')),self.assertRaises(ValueError)):
                reader.readback(registration_path='E:/synthetic/registration.json',registration_sha256='a'*64,
                    capture_reference=dict(path='E:/synthetic/capture.json',sha256='b'*64),
                    publication_reference=dict(path='E:/synthetic/publication.json',sha256='c'*64),
                    output_directory='E:/synthetic/readback',execute=True)


if __name__=='__main__':unittest.main()
