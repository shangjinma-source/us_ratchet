"""Adversarial full physical temporary readback; never a research publication."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_registered_compact_history_runtime_20261009_v1 as runtime
from scripts import ndx_registered_compact_history_independent_readback_20261009_v1 as reader
import test_ndx_registered_compact_history_runtime_20261009_v1_independent_review as physical
import test_ndx_registered_compact_history_independent_readback_20261009_v1 as formula


class IndependentRegisteredReadbackTests(unittest.TestCase):
    def test_host_pending_and_invalid_references_before_any_io(self):
        for mode in ('registration', 'registration_core', 'dependency', 'history', 'publication'):
            deps=deepcopy(reader.DEPENDENCIES)
            if mode=='dependency':deps['history_core']=(deps['history_core'][0],None)
            args=dict(registration_path='E:/synthetic_registration.json',registration_sha256='a'*64,
                history_reference=dict(path='E:/synthetic/history.json',sha256='b'*64),
                publication_reference=dict(path='E:/synthetic/publication.json',sha256='c'*64),
                output_directory='E:/synthetic_readback',execute=True)
            if mode=='registration':args['registration_sha256']=None
            if mode in ('history','publication'):args[mode+'_reference']['sha256']=None
            core=(reader.REGISTRATION_CORE[0],None if mode=='registration_core' else reader.REGISTRATION_CORE[1])
            with (self.subTest(mode=mode),patch.multiple(reader,REGISTRATION_CORE=core,DEPENDENCIES=deps),
                  patch.object(Path,'read_bytes',side_effect=AssertionError('IO before validated pins')),
                  patch.object(Path,'mkdir',side_effect=AssertionError('Namespace before validated pins'))):
                with self.assertRaises(ValueError):reader.readback(**args)

    def test_counts_and_reference_claim_authority_and_dual_baseline_rejected(self):
        for mutate in (
            lambda a:a['observation']['audit']['counts'].update(final_durable_completion_time_verified=True),
            lambda a:a['observation']['payload']['source_hashes'].pop(a['parent']['reader_reference']['path']),
            lambda a:a['observation']['receipt']['input_references']['capture']['reader_reference'].update(sha256='f'*64),
            lambda a:a['observation']['payload']['full_original_sources_preserved']['QQQ']['baseline_sources'].update(
                reference=deepcopy(a['parent']['document']['history']['baseline_references']['QQQ']))):
            a=formula.fixture();mutate(a)
            with self.subTest(mutate=mutate),self.assertRaises((ValueError,KeyError)):formula.reconstruct(a)

    def test_linked_source_and_conflicting_case_alias_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_source_link_') as folder:
            root=Path(folder);original=root/'original';original.write_bytes(b'original')
            item=reader.reference(str(original),reader.sha(b'original'))
            with self.assertRaises(ValueError):reader.consume(item,{str(original).upper():'f'*64})
            linked=root/'linked';linked.symlink_to(original)
            with self.assertRaisesRegex(ValueError,'Linked evidence'):reader.consume(reader.reference(str(linked),item['sha256']),{})
            linked_folder=root/'linked_folder';linked_folder.symlink_to(root,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'Linked evidence'):reader.consume(reader.reference(str(linked_folder/'original'),item['sha256']),{})

    def test_full_physical_namespace_exact_fields_drift_and_failure_retention(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_registered_reader_review_') as folder:
            root=Path(folder);research=root/'research';research.mkdir()
            observation=physical.physical_observation(root);path,digest,reg=physical.registration(root,research,observation)
            with patch.object(runtime,'RESEARCH',research):
                published=runtime.run(registration_path=str(path),registration_sha256=digest,execute=True)
            args=dict(registration_path=str(path),registration_sha256=digest,
                history_reference=published['history_reference'],publication_reference=published['publication_reference'],execute=True)
            with patch.object(reader,'RESEARCH',research):
                # Namespace semantics: even empty side directories and unknown files must block pre-output.
                for i,source_folder in enumerate((Path(reg['output_directory']),Path(observation['payload_reference']['path']).parent)):
                    for kind in ('file','directory'):
                        rogue=source_folder/'extra_evidence';output=research/f'rejected_namespace_{i}_{kind}'
                        if kind=='file':rogue.write_bytes(b'unknown')
                        else:rogue.mkdir()
                        try:
                            with self.assertRaises(ValueError):reader.readback(**args,output_directory=str(output))
                            self.assertFalse(output.exists())
                        finally:
                            if kind=='file':rogue.unlink()
                            else:rogue.rmdir()
                # Rehashing both public anchors cannot conceal non-count history tampering.
                hp=Path(args['history_reference']['path']);pp=Path(args['publication_reference']['path'])
                oldh,oldp=hp.read_bytes(),pp.read_bytes()
                for field,value in (('raw_source_bytes_embedded',True),('last_observed_session','2026-10-09')):
                    document=reader.decode(oldh);document['history'][field]=value;hp.write_bytes(reader.encode(document))
                    forged_history=reader.reference(str(hp),reader.sha(hp.read_bytes()))
                    publication=reader.decode(oldp);publication['history_reference']=forged_history;pp.write_bytes(reader.encode(publication))
                    output=research/f'rejected_tamper_{field}'
                    with self.assertRaises(ValueError):reader.readback(**dict(args,history_reference=forged_history,
                        publication_reference=reader.reference(str(pp),reader.sha(pp.read_bytes()))),output_directory=str(output))
                    self.assertFalse(output.exists());hp.write_bytes(oldh);pp.write_bytes(oldp)
                # Drift after formula reconstruction is checked again before any output namespace.
                real_reconstruct=reader.reconstruct_history
                tzpath=None;tzraw=None
                def drift(**kwargs):
                    nonlocal tzpath,tzraw
                    result=real_reconstruct(**kwargs);tzpath=Path(result['tzif_reference']['path'])
                    tzraw=tzpath.read_bytes();tzpath.write_bytes(tzraw+b'drift');return result
                output=research/'rejected_source_drift'
                try:
                    with patch.object(reader,'reconstruct_history',side_effect=drift),self.assertRaises(ValueError):
                        reader.readback(**args,output_directory=str(output))
                    self.assertFalse(output.exists())
                finally:
                    if tzpath is not None:tzpath.write_bytes(tzraw)
                output=research/'rejected_resource'
                with (patch.object(reader.shutil,'disk_usage',return_value=SimpleNamespace(free=0)),
                      self.assertRaisesRegex(ValueError,'Resource stop before namespace')):
                    reader.readback(**args,output_directory=str(output))
                self.assertFalse(output.exists())
                # Private parent inspector must never use its append function or import cache substitute.
                real_private=reader.private_module
                def private(*pos,**kw):
                    module=real_private(*pos,**kw)
                    if Path(pos[0])==reader.DEPENDENCIES['history_core'][0]:
                        module.append_observation_history_v4=lambda **kw:(_ for _ in ()).throw(AssertionError('Append called'))
                    return module
                output=research/'independent_full_pass'
                with (patch.object(reader,'private_module',side_effect=private),patch.dict('sys.modules',{
                    'backtest.ndx_prospective_observation_parent_history_research':SimpleNamespace(),
                    'backtest.ndx_prospective_observation_parent_history_research_v4':SimpleNamespace()})):
                    report=reader.readback(**args,output_directory=str(output))
                audit=reader.decode(Path(report['path']).read_bytes())
                self.assertEqual((audit['counts']['typed_row_count'],audit['counts']['observation_count'],audit['counts']['gap_count']),(70,2,8))
                self.assertTrue(all(audit[key] is False for key in reader.WRAPPER_FALSE))
                self.assertFalse(audit['append_algorithm_called']);self.assertTrue(audit['entire_history_independently_reconstructed'])
                for source,claim in audit['source_hashes'].items():self.assertEqual(reader.sha(Path(source).read_bytes()),claim)
                failed=research/'independent_failed_retained';real_save=reader.save
                def fail_report(target,value):
                    if target.name=='independent_readback.json':raise ValueError('Injected durable report failure')
                    return real_save(target,value)
                with patch.object(reader,'save',side_effect=fail_report),self.assertRaisesRegex(ValueError,'Injected durable'):
                    reader.readback(**args,output_directory=str(failed))
                self.assertEqual({p.name for p in failed.iterdir()},{'started.json','failure.json'})
                failure=reader.decode((failed/'failure.json').read_bytes())
                self.assertTrue(all(failure[key] is False for key in reader.WRAPPER_FALSE))
                with self.assertRaisesRegex(ValueError,'create-only'):reader.readback(**args,output_directory=str(failed))


if __name__=='__main__':unittest.main()
