"""Coordinated re-sign attacks against genuine registered temporary ancestors."""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_compact_history_runtime_20261009_v2 as runtime
from test_ndx_registered_compact_history_runtime_20261009_v2 import physical_context,run_context


def rewrite(value,old,new):
    if isinstance(value,dict):
        if value==old:return deepcopy(new)
        return {(new if key==old else key):rewrite(item,old,new)for key,item in value.items()}
    if isinstance(value,list):return [rewrite(item,old,new)for item in value]
    return deepcopy(new)if value==old else value


class CoordinatedOriginalEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=TemporaryDirectory(prefix='REGISTERED_COMPACT_V2_COORDINATED_ONLY_')
        cls.root=Path(cls.temporary.name);cls.context=physical_context(cls.root)

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    @contextmanager
    def preserved(self):
        files={p:p.read_bytes()for p in self.root.rglob('*')if p.is_file()}
        directories={p for p in self.root.rglob('*')if p.is_dir()}
        try:yield
        finally:
            for p in self.root.rglob('*'):
                if p.is_file()and p not in files:p.unlink()
            for p in sorted((p for p in self.root.rglob('*')if p.is_dir()and p not in directories),key=lambda p:len(p.parts),reverse=True):p.rmdir()
            for p,raw in files.items():p.write_bytes(raw)

    @contextmanager
    def validators(self):
        research,parentrefs,obsrefs,current,deps,_=self.context
        with patch.multiple(runtime,RESEARCH=research,CURRENT=current,DEPENDENCIES=deps):
            sources={};dependencies={key:runtime.reference(*value)for key,value in deps.items()}
            auxiliary={key:runtime.reference(*value)for key,value in runtime.AUXILIARIES.items()}
            modules=runtime.load_modules(dependencies,auxiliary,sources)
            parent=runtime.parent_documents(parentrefs,sources)
            observation=runtime.observation_documents(obsrefs,sources)
            startedpath=Path(obsrefs['payload_reference']['path']).parent/'started.json'
            startref=runtime.reference(startedpath,runtime.sha(startedpath.read_bytes()))
            started=runtime.decode(startedpath.read_bytes());view=modules['view'].inspect_parent_history_v5(parent)
            yield modules,parent,observation,started,startref,view,sources

    def outer(self,values):
        modules,parent,observation,started,startref,view,sources=values
        runtime.verify_observation_outer(parent,observation,started,startref,view,modules,sources)

    def resign_documents(self,paths,old,new):
        """Update actual artifacts and every reference to each resulting digest."""
        docs={path:rewrite(runtime.decode(path.read_bytes()),old,new)for path in paths}
        if isinstance(old,dict)and set(old)=={'path','sha256'}:
            docs={path:rewrite(rewrite(doc,old['path'],new['path']),old['sha256'],new['sha256'])for path,doc in docs.items()}
        # Dependency order is registration, START, payload/wrapper, receipt/pub, audit.
        for path in paths:
            prior=runtime.reference(path,runtime.sha(path.read_bytes()))
            path.write_bytes(runtime.encode(docs[path]));fresh=runtime.reference(path,runtime.sha(path.read_bytes()))
            for later in paths[paths.index(path)+1:]:docs[later]=rewrite(docs[later],prior,fresh)
            for later in paths[paths.index(path)+1:]:docs[later]=rewrite(docs[later],prior['sha256'],fresh['sha256'])
        return docs

    def test_observer_host_dependencies_and_reference_core_cannot_be_resigned(self):
        with self.preserved(),self.validators()as values:
            self.outer(values)
            _,_,observation,started,startref,_,_=values
            refs=observation['payload']['input_references'];folder=Path(observation['payload_reference']['path']).parent
            paths=[Path(refs['registration']['path']),folder/'started.json',folder/'observation_payload.json',folder/'receipt.json',folder/'independent_readback.json']
            baseline={p:p.read_bytes()for p in paths}
            for old in (refs['dependencies']['parent_view'],refs['reference_core']):
                for p,raw in baseline.items():p.write_bytes(raw)
                replacement=runtime.reference(*runtime.AUXILIARIES['independent_prefix'])
                docs=self.resign_documents(paths,old,replacement)
                changed=list(values)
                changed[2]=deepcopy(observation)
                for role,name in [('payload','observation_payload.json'),('receipt','receipt.json'),('audit','independent_readback.json')]:changed[2][role]=docs[folder/name]
                for role,name in [('payload_reference','observation_payload.json'),('receipt_reference','receipt.json'),('audit_reference','independent_readback.json')]:
                    path=folder/name;changed[2][role]=runtime.reference(path,runtime.sha(path.read_bytes()))
                changed[3]=docs[folder/'started.json'];changed[4]=runtime.reference(folder/'started.json',runtime.sha((folder/'started.json').read_bytes()))
                with self.subTest(host=old['path']),self.assertRaises(ValueError):self.outer(changed)

    def test_capture_runtime_and_dependency_roles_cannot_be_resigned(self):
        with self.preserved(),self.validators()as values:
            modules,_,observation,_,_,_,_=values
            refs=observation['payload']['input_references']['capture'];sources={};inventories=[]
            runtime.capture_inventory(refs,modules['checker'],sources,inventories,modules)
            folder=Path(refs['reference']['path']).parent;audit=Path(refs['readback_reference']['path']).parent
            d=runtime.decode(Path(refs['reference']['path']).read_bytes());inputs=d['input_references']
            paths=[Path(inputs['registration']['path']),folder/'started.json',folder/'capture.json',folder/'publication.json',audit/'started.json',audit/'independent_readback.json']
            baseline={p:p.read_bytes()for p in paths}
            for old in (inputs['runtime'],inputs['dependencies']['parent_view']):
                for p,raw in baseline.items():p.write_bytes(raw)
                self.resign_documents(paths,old,runtime.reference(*runtime.AUXILIARIES['independent_prefix']))
                changed=deepcopy(refs)
                for role in ('reference','publication_reference','readback_reference'):
                    path=Path(changed[role]['path']);changed[role]=runtime.reference(path,runtime.sha(path.read_bytes()))
                with self.subTest(host=old['path']),self.assertRaises(ValueError):runtime.capture_inventory(changed,modules['checker'],{},[],modules)

    def test_later_semantic_failed_attempt_blocks_full_publication_before_namespace(self):
        with self.preserved():
            run_context(self.context)
            research,_,_,_,_,args=self.context
            registration=runtime.decode(Path(args['registration_path']).read_bytes())
            output=research/'coordinated_partial_must_not_publish';registration['output_directory']=str(output)
            path=self.root/'coordinated_partial_registration.json';path.write_bytes(runtime.encode(registration))
            changed=(*self.context[:-1],dict(registration_path=str(path),registration_sha256=runtime.sha(path.read_bytes()),execute=True))
            failed=research/'renamed_after_observation';failed.mkdir()
            (failed/'failure.json').write_bytes(runtime.encode(dict(status='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY')))
            with self.assertRaisesRegex(ValueError,'partial or failed'):run_context(changed)
            self.assertFalse(output.exists());self.assertTrue((failed/'failure.json').is_file())

    def test_resigned_receipt_time_cannot_retain_timely_classification(self):
        with self.preserved(),self.validators()as values:
            _,_,observation,started,_,_,_=values
            p,r=observation['payload'],observation['receipt'];tzif=Path(p['tzif_reference']['path']).read_bytes()
            runtime.verify_observation_timing(p,r,started,tzif)
            folder=Path(observation['payload_reference']['path']).parent
            paths=[folder/'started.json',folder/'observation_payload.json',folder/'receipt.json',folder/'independent_readback.json']
            docs=self.resign_documents(paths,r['publication_check_at_utc'],p['conservative_deadline_utc'])
            with self.assertRaises(ValueError):runtime.verify_observation_timing(docs[folder/'observation_payload.json'],docs[folder/'receipt.json'],docs[folder/'started.json'],tzif)


if __name__=='__main__':unittest.main()
