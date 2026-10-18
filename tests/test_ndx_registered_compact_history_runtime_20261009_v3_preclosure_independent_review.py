"""P3 preclosure attacks. Run only after author hardening readiness.

The author factory has an unexecuted peer stub: these tests establish publisher
rejection ordering only, never a real reader audit or repeated continuation.
"""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_compact_history_runtime_20261009_v3 as runtime
from test_ndx_registered_compact_history_runtime_20261009_v3 import physical_context,run_context


def replace_json(value,old,new):
    if isinstance(value,dict):
        if value==old:return deepcopy(new)
        return {(new if key==old else key):replace_json(item,old,new)for key,item in value.items()}
    if isinstance(value,list):return [replace_json(item,old,new)for item in value]
    return deepcopy(new)if value==old else value


def resign_in_order(paths,documents):
    """Canonical-save actual files and update later reference/hash associations.

    Caller orders START -> wrapper -> publication -> reader START -> audit,
    optionally prefixed by a changed registration. Does not fabricate roles.
    """
    documents=deepcopy(documents)
    for index,path in enumerate(paths):
        before=runtime.reference(path,runtime.sha(path.read_bytes()))
        path.write_bytes(runtime.encode(documents[path]))
        after=runtime.reference(path,runtime.sha(path.read_bytes()))
        for later in paths[index+1:]:
            documents[later]=replace_json(documents[later],before,after)
            documents[later]=replace_json(documents[later],before['sha256'],after['sha256'])
    return documents


def coordinated_source_omission(paths,omitted_path):
    """Prepared primitive for a genuine saved P3/R2 parent, not a fake audit.

    Requires omission present in every declared map. The caller must first show
    the unchanged saved parent passes the exact validator, then test rejection.
    No test claims this utility alone verifies independent derived closure.
    """
    documents={path:runtime.decode(path.read_bytes())for path in paths}
    for path,doc in documents.items():
        claims=doc.get('source_hashes')
        if claims is not None:
            if omitted_path not in claims:raise ValueError('Omitted mandatory source absent from baseline '+str(path))
            del claims[omitted_path]
    return resign_in_order(paths,documents)


class PublisherPreclosureIndependentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=TemporaryDirectory(prefix='P3_PRECLOSURE_REGISTERED_ONLY_')
        cls.root=Path(cls.temporary.name);cls.context=physical_context(cls.root)
        # A real complete registered input chain must publish successfully first.
        cls.baseline=run_context(cls.context)

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    @contextmanager
    def preserved(self):
        files={p:p.read_bytes()for p in self.root.rglob('*')if p.is_file()}
        dirs={p for p in self.root.rglob('*')if p.is_dir()}
        try:yield
        finally:
            for path in self.root.rglob('*'):
                if path.is_file()and path not in files:path.unlink()
            for path in sorted((p for p in self.root.rglob('*')if p.is_dir()and p not in dirs),key=lambda p:len(p.parts),reverse=True):path.rmdir()
            for path,raw in files.items():path.write_bytes(raw)

    def test_unknown_binding_runtime_reader_rejected_before_trap_claim_consumption(self):
        research,parent,observation,current,args,binding=self.context
        for kind in ('unknown_binding','unknown_runtime','unknown_reader','parent_extra_ref'):
            with self.subTest(kind=kind),self.preserved():
                trap=self.root/(kind+'_MUST_NOT_BE_READ.bin');trap.write_bytes(b'Untrusted immutable claim must not be followed.\n')
                trapref=runtime.reference(trap,runtime.sha(trap.read_bytes()))
                refs=deepcopy(parent)
                paths=[Path(refs[role]['path'])for role in ('reference','publication_reference','readback_reference')]
                docs={path:runtime.decode(path.read_bytes())for path in paths}
                unknownpath=self.root/(kind+'_peer.py');unknownpath.write_bytes(b'Unknown implementation bytes, never approved.\n')
                unknown=runtime.reference(unknownpath,runtime.sha(unknownpath.read_bytes()))
                for doc in docs.values():
                    doc['source_hashes'][str(trap)]=trapref['sha256']
                    if kind=='unknown_binding':
                        doc['implementation_pair_binding_reference']=unknown
                        doc['ancestry_contract_reference']=binding['contract_reference']
                    if kind=='unknown_runtime':doc['input_references']['runtime']=unknown
                    if kind=='parent_extra_ref':doc['extra_evidence']=deepcopy(trapref)
                if kind=='unknown_reader':
                    refs['reader_reference']=unknown;docs[paths[2]]['reader_sha256']=unknown['sha256']
                resign_in_order(paths,docs)
                for role in ('reference','publication_reference','readback_reference'):
                    path=Path(refs[role]['path']);refs[role]=runtime.reference(path,runtime.sha(path.read_bytes()))
                registration=runtime.decode(Path(args['registration_path']).read_bytes());registration['parent']=refs
                output=research/(kind+'_output_must_not_exist');registration['output_directory']=str(output)
                path=self.root/(kind+'_daily_registration.json');path.write_bytes(runtime.encode(registration))
                changed_args=dict(args,registration_path=str(path),registration_sha256=runtime.sha(path.read_bytes()))
                changed=(research,refs,observation,current,changed_args,binding)
                reads=[];consumptions=[];real_read=Path.read_bytes;real_consume=runtime.consume
                def read(path):
                    if path in (trap,unknownpath):reads.append(str(path));raise AssertionError('Trap source/peer read before role rejection')
                    return real_read(path)
                def consume(item,sources):
                    if item.get('path')in(str(trap),str(unknownpath)):consumptions.append(item);raise AssertionError('Trap claim/peer followed before role rejection')
                    return real_consume(item,sources)
                with patch.object(Path,'read_bytes',read),patch.object(runtime,'consume',side_effect=consume):
                    with self.assertRaises(ValueError):run_context(changed)
                self.assertEqual(reads,[]);self.assertEqual(consumptions,[]);self.assertFalse(output.exists())

    def test_payload_and_capture_shape_extra_refs_do_not_grant_claim_read_permission(self):
        research,parent,observation,current,args,binding=self.context
        for kind in ('observation_payload','capture_wrapper'):
            with self.subTest(kind=kind),self.preserved():
                trap=self.root/(kind+'_EXTRA_REF_MUST_NOT_BE_READ.bin');trap.write_bytes(b'Extra schema ref is not permission.\n')
                trapref=runtime.reference(trap,runtime.sha(trap.read_bytes()))
                obsrefs=deepcopy(observation);obsfolder=Path(obsrefs['payload_reference']['path']).parent
                obspaths=[obsfolder/'started.json',obsfolder/'observation_payload.json',obsfolder/'receipt.json',obsfolder/'independent_readback.json']
                obsdocs={path:runtime.decode(path.read_bytes())for path in obspaths}
                if kind=='capture_wrapper':
                    caprefs=deepcopy(obsdocs[obspaths[1]]['input_references']['capture'])
                    capfolder=Path(caprefs['reference']['path']).parent;auditfolder=Path(caprefs['readback_reference']['path']).parent
                    cappaths=[capfolder/'started.json',capfolder/'capture.json',capfolder/'publication.json',auditfolder/'started.json',auditfolder/'independent_readback.json']
                    capdocs={path:runtime.decode(path.read_bytes())for path in cappaths}
                    capdocs[capfolder/'capture.json']['extra_evidence']=deepcopy(trapref)
                    for path in cappaths:
                        if 'source_hashes'in capdocs[path]:capdocs[path]['source_hashes'][str(trap)]=trapref['sha256']
                    resign_in_order(cappaths,capdocs)
                    for role in ('reference','publication_reference','readback_reference'):
                        old=caprefs[role];path=Path(old['path']);new=runtime.reference(path,runtime.sha(path.read_bytes()))
                        for obspath in obspaths:
                            obsdocs[obspath]=replace_json(obsdocs[obspath],old,new)
                            obsdocs[obspath]=replace_json(obsdocs[obspath],old['sha256'],new['sha256'])
                else:obsdocs[obspaths[1]]['extra_evidence']=deepcopy(trapref)
                for doc in obsdocs.values():doc['source_hashes'][str(trap)]=trapref['sha256']
                resign_in_order(obspaths,obsdocs)
                for role in ('payload_reference','receipt_reference','audit_reference'):
                    path=Path(obsrefs[role]['path']);obsrefs[role]=runtime.reference(path,runtime.sha(path.read_bytes()))
                registration=runtime.decode(Path(args['registration_path']).read_bytes());registration['observation']=obsrefs
                output=research/(kind+'_output_must_not_exist');registration['output_directory']=str(output)
                path=self.root/(kind+'_extra_registration.json');path.write_bytes(runtime.encode(registration))
                changed_args=dict(args,registration_path=str(path),registration_sha256=runtime.sha(path.read_bytes()))
                changed=(research,parent,obsrefs,current,changed_args,binding)
                reads=[];claims=[];real_read=Path.read_bytes;real_consume=runtime.consume
                def read(path):
                    if path==trap:reads.append(str(path));raise AssertionError('Extra schema reference authorized trap IO')
                    return real_read(path)
                def consume(item,sources):
                    if item.get('path')==str(trap):claims.append(item);raise AssertionError('Extra schema reference authorized trap claim')
                    return real_consume(item,sources)
                with patch.object(Path,'read_bytes',read),patch.object(runtime,'consume',side_effect=consume):
                    with self.assertRaises(ValueError):run_context(changed)
                self.assertEqual(reads,[]);self.assertEqual(claims,[]);self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
