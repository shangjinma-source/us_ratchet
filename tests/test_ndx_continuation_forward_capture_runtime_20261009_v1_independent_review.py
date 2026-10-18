"""Orchestration only: genuine V3/ddd and host kernels, controlled R replay stub.

No real shared R2 execution, six-consumer completion or14->15 claim is made.
"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backtest import ndx_compact_implementation_pair_binding_research_v1 as binder
from backtest import ndx_continuation_consumer_role_registry_research_v1 as registry
from scripts import ndx_prospective_observation_writer_v3_20261009 as old_writer
from scripts import ndx_continuation_forward_capture_runtime_20261009_v1 as producer


def pipeline_fixture(root):
    root=Path(root);research=root/'research';research.mkdir()
    def identity(name):
        path=root/(name+'.identity');path.write_bytes(('UNEXECUTED_ORCHESTRATION_IDENTITY '+name+'\n').encode())
        return producer.reference(str(path),producer.digest(path.read_bytes()))
    peer=identity('pair_publisher');stub=identity('shared_reader')
    algorithms={role:{key:identity('algorithm_'+role+'_'+key) for key in roles}
        for role,roles in binder.DEPENDENCY_ROLES.items()}
    contract=producer.reference(str(producer.ANCESTRY_CONTRACT[0]),producer.ANCESTRY_CONTRACT[1])
    bpath=root/'B.json';bref=producer.reference(str(bpath),'a'*64)
    binding=dict(schema=binder.SCHEMA,family=binder.FAMILY,protocol=binder.PROTOCOL,role=binder.ROLE,
        publisher_reference=peer,independent_reader_reference=stub,contract_reference=contract,
        publisher_dependency_references=algorithms['publisher'],reader_dependency_references=algorithms['independent_reader'],
        approved_legacy_binding_references=[],**binder.FLAGS)
    bpath.write_bytes(producer.encode(binding));bref['sha256']=producer.digest(bpath.read_bytes())
    pair=binder.inspect_pair_binding(binding=binding,binding_reference=bref,host_binding_reference=bref,
        self_role='independent_reader',self_reference=stub,expected_contract_reference=contract,
        expected_algorithm_dependencies=algorithms)
    consumers={role:(producer.reference(str(producer.SOURCE),producer.LOADED_SHA)
        if role=='capture_publisher' else identity('consumer_'+role)) for role in registry.CONSUMER_ROLES}
    cpath=root/'C.json';document=dict(schema=registry.SCHEMA,family=registry.FAMILY,
        protocol=registry.PROTOCOL,role=registry.ROLE,implementation_pair_binding_reference=bref,
        ancestry_contract_reference=contract,consumer_references=consumers,**registry.FLAGS)
    cpath.write_bytes(producer.encode(document));cref=producer.reference(str(cpath),producer.digest(cpath.read_bytes()))
    cview=registry.inspect_consumer_roles(registry=document,registry_reference=cref,
        host_registry_reference=cref,bound_pair=pair)
    parentrefs=deepcopy(old_writer.PARENT_BOUND);sources={}
    parent={role:deepcopy(ref) for role,ref in parentrefs.items()}
    for role,name in [('reference','document'),('publication_reference','publication'),('readback_reference','readback')]:
        parent[name]=producer.decode(producer.consume(parentrefs[role],sources))
        for path,value in parent[name]['source_hashes'].items():producer.consume(producer.reference(path,value),sources)
    producer.consume(parentrefs['reader_reference'],sources)
    raw={key:producer.consume(item,{})for key,item in producer.configured(producer.DEPENDENCIES).items()}
    view=producer.private_core(raw).parent_view.inspect_parent_history_v5(parent)
    current={}
    for ticker in ('QQQ','SPY'):
        path=root/(ticker+'.live.csv');path.write_bytes(Path(view['accounted_baseline_references'][ticker]['path']).read_bytes());current[ticker]=path
    # All stub-returned claims are actual bounded files, but ancestry authentication
    # is expressly absent. No active compact publisher/reader source is loaded.
    for ref in (peer,stub,bref,cref,contract,*consumers.values(),
            *(item for group in algorithms.values() for item in group.values())):
        producer.consume(ref,sources)
    calls=[]
    def guard():
        calls.append('guard')
        for path,digest in sources.items():producer.consume(producer.reference(path,digest),{})
    def replay(**kwargs):
        calls.append('controlled_replay_stub')
        assert kwargs['parent_references']==parentrefs
        assert kwargs['implementation_pair_binding_path']==str(bpath)
        assert kwargs['consumer_role_registry_path']==str(cpath)
        return dict(status='READ_ONLY_WHOLE_ANCESTRY_RECONSTRUCTION_PASS',bound_pair=pair,
            consumer_registry_view=cview,consumer_registry_core_reference=producer.reference(*map(str,producer.CONSUMER_REGISTRY_CORE)),
            consumer_metadata_contract_reference=producer.reference(*map(str,producer.CONSUMER_METADATA_CORE)),
            parent_envelope=parent,parent_view=view,sources=deepcopy(sources),final_guard=guard)
    output=research/'capture'
    regpath=root/'registration.json'
    value=dict(schema='FORWARD_CAPTURE_RUNTIME_REGISTRATION_V2',runtime_reference=consumers['capture_publisher'],
        dependency_references=producer.configured(producer.DEPENDENCIES),parent=parentrefs,
        output_directory=str(output))
    # Registration flags come from its actual fixed contract, not business flags.
    from backtest import ndx_forward_capture_runtime_registration_research_v2 as registration
    value={key:value[key]for key in ('schema','runtime_reference','dependency_references','parent','output_directory')}
    value.update(registration.FLAGS);regpath.write_bytes(producer.encode(value))
    args=dict(registration_path=str(regpath),registration_sha256=producer.digest(regpath.read_bytes()),
        implementation_pair_binding_path=str(bpath),implementation_pair_binding_sha256=bref['sha256'],
        consumer_role_registry_path=str(cpath),consumer_role_registry_sha256=cref['sha256'],execute=True)
    return dict(root=root,research=research,current=current,stub=stub,args=args,output=output,
        replay=SimpleNamespace(verify_saved_parent_ancestry=replay),calls=calls)


def run_pipeline(context):
    original=producer.compile_private
    def compile_role(path,raw,expected,replacements=()):
        if str(path)==context['stub']['path']:
            assert producer.digest(raw)==expected==context['stub']['sha256']
            return context['replay']
        return original(path,raw,expected,replacements)
    with patch.multiple(producer,RESEARCH=context['research'],CURRENT=context['current'],
            SHARED_ANCESTRY_VERIFIER=(Path(context['stub']['path']),context['stub']['sha256'])), \
            patch.object(producer,'compile_private',side_effect=compile_role), \
            patch.object(producer,'now',side_effect=['2026-10-09T20:02:00+00:00','2026-10-09T20:02:01+00:00']):
        return producer.run(**context['args'])


class ContinuationCaptureIndependentPipelineTests(unittest.TestCase):
    def test_real_business_no_new_pipeline_headers_sources_and_createonly(self):
        with TemporaryDirectory(prefix='C_CAPTURE_CONTROLLED_REPLAY_ONLY_')as directory:
            context=pipeline_fixture(Path(directory));result=run_pipeline(context)
            d=producer.decode(Path(result['capture_reference']['path']).read_bytes())
            p=producer.decode(Path(result['publication_reference']['path']).read_bytes())
            s=producer.decode((context['output']/'started.json').read_bytes())
            self.assertEqual(d['plan']['status'],'NO_NEW_SESSION')
            self.assertEqual(len(d['plan']['known_typed_rows']),69)
            self.assertEqual(set(x.name for x in context['output'].iterdir()),
                {'started.json','QQQ.csv','SPY.csv','New_York.tzif','capture.json','publication.json'})
            from backtest import ndx_continuation_consumer_metadata_research_v1 as metadata
            for key in metadata.METADATA_KEYS:self.assertEqual(s[key],d[key]);self.assertEqual(p[key],d[key])
            self.assertEqual(s['input_references'],d['input_references'])
            self.assertNotIn('input_references',p)  # Original capture publication shape is retained.
            self.assertEqual(p['source_hashes'],d['source_hashes'])
            for key in producer.FLAGS:
                for obj in (s,d,p):self.assertIs(obj[key],False)
            for path,digest in d['source_hashes'].items():self.assertEqual(producer.digest(Path(path).read_bytes()),digest)
            for path in context['current'].values():self.assertNotIn(str(path),d['source_hashes'])
            self.assertGreater(context['calls'].count('guard'),5)
            with self.assertRaisesRegex(ValueError,'Create-only'):run_pipeline(context)

    def test_own_start_drift_and_extra_file_leave_failure_and_block_retry(self):
        for attack in ('own_start','extra_file','live_drift'):
            with self.subTest(attack=attack),TemporaryDirectory(prefix='C_CAPTURE_FAILURE_ONLY_')as directory:
                context=pipeline_fixture(Path(directory));original=producer.save_bytes
                def write(path,raw):
                    result=original(path,raw)
                    if attack=='own_start'and path.name=='started.json':path.write_bytes(raw+b'\n')
                    if attack=='extra_file'and path.name=='QQQ.csv':(context['output']/'unexpected.json').write_bytes(b'{}')
                    if attack=='live_drift'and path.name=='QQQ.csv':context['current']['SPY'].write_bytes(b'changed')
                    return result
                with patch.object(producer,'save_bytes',side_effect=write),self.assertRaises(ValueError):run_pipeline(context)
                failure=producer.decode((context['output']/'failure.json').read_bytes())
                self.assertEqual(failure['status'],'FAILED_DO_NOT_CONSUME')
                self.assertFalse((context['output']/'publication.json').exists())
                for key in producer.FLAGS:self.assertIs(failure[key],False)
                with self.assertRaisesRegex(ValueError,'Create-only'):run_pipeline(context)


if __name__=='__main__':unittest.main()
