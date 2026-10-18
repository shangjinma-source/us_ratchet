"""Full physical V5 capture publisher audits, disposable test namespaces only."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from scripts import ndx_registered_forward_capture_runtime_20261009_v2 as capture
from scripts import ndx_prospective_observation_writer_v3_20261009 as oldwriter
from backtest import ndx_forward_capture_runtime_registration_research_v2 as registration_core
from backtest import ndx_prospective_history_parent_view_research_v5 as view
import test_ndx_registered_forward_capture_runtime_20261009_v1_independent_review as physical
from ndx_v5_physical_parent_fixture import physical_gap_parent,envelope,reference

CORE_SHA='ddd570ab3a79832ef6d530693ade9ac37b8f82c18b13efe322558099a04a7e5e'
REGISTRATION_SHA='fc907ddff33988b3f3e29f4585c32ae7b2e743ea9f6abe29055772ce0f0876cd'


def dependencies():
    deps=deepcopy(capture.DEPENDENCIES);deps['capture_core']=(deps['capture_core'][0],CORE_SHA)
    return deps


def registered(root,research,parent,name):
    value=dict(schema=registration_core.SCHEMA,runtime_reference=dict(path=str(capture.SOURCE),sha256=capture.LOADED_SHA),
        dependency_references=capture.configured(dependencies()),parent=deepcopy(parent),output_directory=str(research/name),**registration_core.FLAGS)
    path=root/(name+'_registration.json');path.write_bytes(capture.encode(value))
    return dict(registration_path=str(path),registration_sha256=capture.digest(path.read_bytes()),execute=True),value


def current_files(root,parent,name):
    normalized=view.inspect_parent_history_v5(envelope(parent));folder=root/(name+'_current');folder.mkdir()
    refs=normalized['full_capture_source_references'];current={}
    for ticker,item in refs.items():current[ticker]=folder/(ticker+'.csv');current[ticker].write_bytes(Path(item['path']).read_bytes())
    return current


def run(root,research,parent,name,current,start='2026-10-12T20:03:00+00:00',end='2026-10-12T20:03:01+00:00'):
    args,value=registered(root,research,parent,name)
    with (patch.multiple(capture,RESEARCH=research,CURRENT=current,DEPENDENCIES=dependencies(),
        REGISTRATION_CORE=(capture.REGISTRATION_CORE[0],REGISTRATION_SHA)),patch.object(capture,'now',side_effect=[start,end])):
        return capture.run(**args),value


def replace_claim(value,path,digest):
    if type(value)is dict:
        if value.get('path')==path and 'sha256'in value:value['sha256']=digest
        if path in value:value[path]=digest
        for item in value.values():replace_claim(item,path,digest)
    elif type(value)is list:
        for item in value:replace_claim(item,path,digest)


def resign_parent(parent,artifact_path,raw,mutate_history=None):
    """Re-sign a synthetic parent after changing an artifact, preserving closure."""
    parent=deepcopy(parent);docs=envelope(parent);folder=Path(parent['reference']['path']).parent
    if mutate_history:mutate_history(docs['document']['history'])
    started=capture.decode((folder/'started.json').read_bytes())
    if mutate_history:
        for value in (started,docs['document'],docs['publication'],docs['readback']):
            value['input_references']['capture']=deepcopy(docs['document']['history']['capture_references'])
    Path(artifact_path).write_bytes(raw);digest=capture.digest(raw)
    for value in (started,docs['document'],docs['publication'],docs['readback']):replace_claim(value,str(artifact_path),digest)
    (folder/'started.json').write_bytes(capture.encode(started))
    for value in (docs['document'],docs['publication'],docs['readback']):replace_claim(value,str(folder/'started.json'),reference(folder/'started.json')['sha256'])
    for role,key,following in (('reference','document',('publication','readback')),('publication_reference','publication',('readback',)),('readback_reference','readback',())):
        path=Path(parent[role]['path']);path.write_bytes(capture.encode(docs[key]));parent[role]=reference(path)
        for next_key in following:replace_claim(docs[next_key],str(path),parent[role]['sha256'])
    return parent


def resign_upstream_capture_metadata(parent,key,value):
    h=envelope(parent)['document']['history'];refs=h['capture_references'];docs=envelope(refs)
    docs['document'][key]=value
    replacement=resign_parent(parent,refs['reference']['path'],capture.encode(docs['document']))
    new_capture=reference(refs['reference']['path'])
    replace_claim(docs['publication'],refs['reference']['path'],new_capture['sha256'])
    replacement=resign_parent(replacement,refs['publication_reference']['path'],capture.encode(docs['publication']))
    new_publication=reference(refs['publication_reference']['path'])
    replace_claim(docs['readback'],refs['reference']['path'],new_capture['sha256'])
    replace_claim(docs['readback'],refs['publication_reference']['path'],new_publication['sha256'])
    return resign_parent(replacement,refs['readback_reference']['path'],capture.encode(docs['readback']))


class IndependentRegisteredCaptureV2Tests(unittest.TestCase):
    def test_coordinated_resigned_original_capture_metadata_cannot_change_contract(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_V5_ORIGINAL_METADATA_')as folder:
            root=Path(folder);research=root/'research';research.mkdir();parent,_=physical_gap_parent(root,research)
            h=envelope(parent)['document']['history'];refs=h['capture_references']
            changed_paths=[Path(parent[k]['path'])for k in ('reference','publication_reference','readback_reference')]
            changed_paths+=[Path(refs[k]['path'])for k in ('reference','publication_reference','readback_reference')]
            changed_paths+=[Path(parent['reference']['path']).parent/'started.json']
            before={path:path.read_bytes()for path in changed_paths}
            for key,value in (('external_clock_attestation_verified',True),('quote_source_type','NETWORK_QUOTE_VERIFIED'),('extra_authority',True)):
                try:
                    forged=resign_upstream_capture_metadata(parent,key,value)
                    view.inspect_parent_history_v5(envelope(forged))
                    current=current_files(root,forged,key)
                    with self.subTest(key=key),self.assertRaisesRegex(ValueError,'complete wrapper contract'):
                        run(root,research,forged,'reject_'+key,current)
                    self.assertFalse((research/('reject_'+key)).exists())
                finally:
                    for path,raw in before.items():path.write_bytes(raw)

    def test_every_pending_host_pin_is_rejected_before_source_io(self):
        for role in ('registration','reference',*capture.DEPENDENCIES):
            deps=dependencies()
            if role in deps:deps[role]=(deps[role][0],None)
            with (self.subTest(role=role),patch.multiple(capture,DEPENDENCIES=deps,
                REGISTRATION_CORE=(capture.REGISTRATION_CORE[0],None if role=='registration'else REGISTRATION_SHA),
                REFERENCE_CORE=(capture.REFERENCE_CORE[0],None if role=='reference'else capture.REFERENCE_CORE[1])),
                patch.object(Path,'read_bytes',side_effect=AssertionError('Read before pending host validation')),
                self.assertRaises(ValueError)):
                capture.run(registration_path='E:/synthetic/registration.json',registration_sha256='a'*64,execute=True)

    def test_complete_v3_v4_v5_zero_one_and_mixed_parent_schemas(self):
        for kind in ('v3','v4','v5zero','v5one','v5mixed'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_V5_CAPTURE_')as folder:
                root=Path(folder);research=root/'research';research.mkdir()
                if kind=='v3':parent=deepcopy(oldwriter.PARENT_BOUND)
                elif kind=='v4':parent=physical.compact_parent(root,research)
                else:parent,_=physical_gap_parent(root,research,source_dates={'v5zero':('2026-10-09',),'v5one':('2026-10-09','2026-10-12'),'v5mixed':('2026-10-09','2026-10-12','2026-10-13')}[kind])
                if kind in ('v3','v4'):
                    zero_current=current_files(root,parent,kind+'_zero')
                    zero,_=run(root,research,parent,kind+'_zero_capture',zero_current)
                    self.assertEqual(capture.decode(Path(zero['capture_reference']['path']).read_bytes())['plan']['status'],'NO_NEW_SESSION')
                current=current_files(root,parent,kind)
                if kind in ('v3','v4'):
                    day='2026-10-08'if kind=='v3'else'2026-10-09'
                    for path in current.values():
                        with path.open('ab')as file:file.write((day+',100,110,90,100,1000\n').encode())
                result,value=run(root,research,parent,kind+'_capture',current)
                doc=capture.decode(Path(result['capture_reference']['path']).read_bytes());plan=doc['plan']
                self.assertEqual(plan['status'],'NO_NEW_SESSION'if kind=='v5zero'else'BLOCKED_SOURCE_DIAGNOSTICS'if kind=='v5mixed'else'ONE_NEW_SESSION_CAPTURE_CANDIDATE')
                self.assertEqual(plan['actual_parent_schema'],envelope(parent)['document']['history']['schema'])
                self.assertEqual(plan['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
                self.assertEqual({p.name for p in Path(value['output_directory']).iterdir()},{'started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'})
                self.assertTrue(all(doc[k]is False for k in capture.FLAGS))
                for live in current.values():self.assertNotIn(str(live),doc['source_hashes']);live.write_bytes(b'changed live after capture')
                for source,digest in doc['source_hashes'].items():self.assertEqual(reference(source)['sha256'],digest)
                with self.assertRaisesRegex(ValueError,'Create-only'):run(root,research,parent,kind+'_capture',current)

    def test_v5_evidence_artifact_must_match_declared_summary_and_derivation(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_V5_EVIDENCE_ATTACK_')as folder:
            root=Path(folder);research=root/'research';research.mkdir();parent,_=physical_gap_parent(root,research)
            item=envelope(parent)['document']['history']['accounted_prefix_evidence_references']['QQQ']
            forged=resign_parent(parent,item['path'],b'{"forged":true}\n')
            # All source hashes and structural declarations are internally consistent.
            view.inspect_parent_history_v5(envelope(forged))
            current=current_files(root,forged,'forged')
            with self.assertRaises(ValueError):run(root,research,forged,'evidence_forgery',current)
            self.assertFalse((research/'evidence_forgery').exists())

    def test_true_prior_flat_source_state_and_full_capture_reader_association_must_match(self):
        for mode in ('prior_state','capture_audit'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_V5_PARENT_ASSOCIATION_')as folder:
                root=Path(folder);research=root/'research';research.mkdir();parent,_=physical_gap_parent(root,research)
                h=envelope(parent)['document']['history'];artifact=h['accounted_prefix_evidence_references']['QQQ']['path']
                def mutate(history):
                    if mode=='prior_state':
                        full=history['full_capture_source_references']['QQQ'];history['prior_state_preserved']['source_hashes'][full['path']]=full['sha256']
                    else:history['capture_references']['readback_reference']=deepcopy(history['parent_references']['readback_reference'])
                forged=resign_parent(parent,artifact,Path(artifact).read_bytes(),mutate)
                view.inspect_parent_history_v5(envelope(forged))
                current=current_files(root,forged,mode)
                with self.assertRaises(ValueError):run(root,research,forged,mode+'_forgery',current)
                self.assertFalse((research/(mode+'_forgery')).exists())

    def test_v5_inventory_resource_clock_and_durability_failures_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_V5_CAPTURE_GUARDS_')as folder:
            root=Path(folder);research=root/'research';research.mkdir();parent,_=physical_gap_parent(root,research)
            current=current_files(root,parent,'guards');parent_folder=Path(parent['reference']['path']).parent
            extra=parent_folder/'unbound_item'
            for kind in ('file','directory','link'):
                if kind=='file':extra.write_bytes(b'unknown')
                elif kind=='directory':extra.mkdir()
                else:
                    secret=root/'secret';secret.write_bytes(b'never read linked item');extra.symlink_to(secret)
                real_read=Path.read_bytes
                def no_extra(path):
                    if path==extra:raise AssertionError('Read unknown linked namespace item')
                    return real_read(path)
                try:
                    with patch.object(Path,'read_bytes',no_extra),self.assertRaises(ValueError):run(root,research,parent,'reject_'+kind,current)
                    self.assertFalse((research/('reject_'+kind)).exists())
                finally:
                    if kind=='directory':extra.rmdir()
                    else:extra.unlink()
            with patch.object(capture.shutil,'disk_usage',return_value=SimpleNamespace(free=0)),self.assertRaisesRegex(ValueError,'RESOURCE_STOP'):
                run(root,research,parent,'reject_resource',current)
            self.assertFalse((research/'reject_resource').exists())
            with self.assertRaises(ValueError):run(root,research,parent,'failed_clock',current,start='2026-10-12T20:01:00+00:00')
            self.assertTrue((research/'failed_clock'/'failure.json').is_file())
            with self.assertRaisesRegex(ValueError,'Create-only'):run(root,research,parent,'failed_clock',current)
            real_save=capture.save
            def drift_start(path,value):
                result=real_save(path,value)
                if path.name=='started.json':path.write_bytes(path.read_bytes()+b' ')
                return result
            with patch.object(capture,'save',side_effect=drift_start),self.assertRaisesRegex(ValueError,'Source SHA changed'):
                run(root,research,parent,'failed_own_start',current)
            failure=capture.decode((research/'failed_own_start'/'failure.json').read_bytes())
            self.assertTrue(all(failure[k]is False for k in capture.FLAGS))
            self.assertTrue((research/'failed_own_start'/'started.json').is_file())
            # A malicious parent readback may add an apparently hashed live source.
            # Reject it before read_bytes, rather than reading and checking later.
            forged=deepcopy(parent);audit_path=Path(parent['readback_reference']['path'])
            audit=capture.decode(audit_path.read_bytes());live=current['QQQ']
            audit['source_hashes'][str(live)]=reference(live)['sha256'];audit_path.write_bytes(capture.encode(audit))
            forged['readback_reference']=reference(audit_path);real_read=Path.read_bytes
            def no_live(path):
                if path==live:raise AssertionError('Live source read before permanent-claim rejection')
                return real_read(path)
            with patch.object(Path,'read_bytes',no_live),self.assertRaisesRegex(ValueError,'Mutable cache'):
                run(root,research,forged,'reject_live_claim',current)
            self.assertFalse((research/'reject_live_claim').exists())

    def test_every_upstream_layer_start_and_namespace_is_rechecked_after_capture_begins(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ONLY_V5_FINAL_LAYER_GUARDS_')as folder:
            root=Path(folder);research=root/'research';research.mkdir();parent,_=physical_gap_parent(root,research)
            current=current_files(root,parent,'layer_guards');h=envelope(parent)['document']['history']
            refs=h['capture_references'];prior=h['parent_references']
            starts=[Path(item['path']).parent/'started.json'for item in (
                parent['reference'],parent['readback_reference'],refs['reference'],refs['readback_reference'],prior['reference'],prior['readback_reference'])]
            for index,target in enumerate(starts):
                before=target.read_bytes();calls=[];args,_=registered(root,research,parent,'failed_layer_'+str(index))
                def clock():
                    if not calls:target.write_bytes(before+b' ')
                    calls.append(1);return '2026-10-12T20:03:00+00:00'
                try:
                    with (patch.multiple(capture,RESEARCH=research,CURRENT=current,DEPENDENCIES=dependencies(),
                        REGISTRATION_CORE=(capture.REGISTRATION_CORE[0],REGISTRATION_SHA)),patch.object(capture,'now',side_effect=clock),
                        self.assertRaisesRegex(ValueError,'Source SHA changed')):
                        capture.run(**args)
                    self.assertTrue((research/('failed_layer_'+str(index))/'failure.json').is_file())
                finally:target.write_bytes(before)
            extra=Path(refs['reference']['path']).parent/'late_unbound_directory';calls=[]
            def clock_side_item():
                if not calls:extra.mkdir()
                calls.append(1);return '2026-10-12T20:03:00+00:00'
            args,_=registered(root,research,parent,'failed_capture_side_item')
            try:
                with (patch.multiple(capture,RESEARCH=research,CURRENT=current,DEPENDENCIES=dependencies(),
                    REGISTRATION_CORE=(capture.REGISTRATION_CORE[0],REGISTRATION_SHA)),patch.object(capture,'now',side_effect=clock_side_item),
                    self.assertRaisesRegex(ValueError,'namespace inventory')):
                    capture.run(**args)
            finally:extra.rmdir()
            self.assertTrue((research/'failed_capture_side_item'/'failure.json').is_file())
            with patch.object(capture,'MAX_PARENT_DEPTH',1),self.assertRaisesRegex(ValueError,'maximum depth'):
                run(root,research,parent,'reject_ancestry_limit',current)
            self.assertFalse((research/'reject_ancestry_limit').exists())


if __name__=='__main__':unittest.main()
