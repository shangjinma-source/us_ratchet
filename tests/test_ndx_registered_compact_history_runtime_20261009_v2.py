"""Temporary-only new compact publication with a future core pin patched in tests."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_compact_history_runtime_20261009_v2 as runtime
from backtest import ndx_compact_history_runtime_registration_research_v1 as registration
from backtest import ndx_prospective_observation_compact_append_research_v2 as core
from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy
from ndx_registered_v5_observation_fixture_v2 import physical_registered_v5_observation

CORE_SHA='44225869dba5f852809c02390bc455c07fa3596383bf8b5fc992352f03bdddf9'


def physical_context(root,name='compact_v2'):
    research=root/'research'
    parent,observation,original=physical_registered_v5_observation(root,research)
    current=original['current']
    dependencies=deepcopy(runtime.DEPENDENCIES);dependencies['history_core']=(dependencies['history_core'][0],CORE_SHA)
    value=dict(schema=registration.SCHEMA,runtime_reference=runtime.reference(runtime.SOURCE,runtime.LOADED_SHA),
        dependency_references={key:runtime.reference(*item)for key,item in dependencies.items()},parent=parent,observation=observation,
        output_directory=str(research/name),**registration.FLAGS)
    path=root/(name+'_registration.json');path.write_bytes(runtime.encode(value))
    return research,parent,observation,current,dependencies,dict(registration_path=str(path),registration_sha256=runtime.sha(path.read_bytes()),execute=True)


def run_context(context):
    research,_,_,current,deps,args=context
    with patch.multiple(runtime,RESEARCH=research,CURRENT=current,DEPENDENCIES=deps):return runtime.run(**args)


class CompactRuntimeV2DraftTests(unittest.TestCase):
    def test_all_host_pins_are_checked_before_io_and_default_does_not_publish(self):
        kwargs=dict(registration_path='E:/synthetic/registration.json',registration_sha256='a'*64)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Source IO')):
            self.assertEqual(runtime.run(**kwargs),dict(status='NOT_EXECUTED'))
            pending=deepcopy(runtime.DEPENDENCIES);pending['history_core']=(pending['history_core'][0],None)
            with patch.object(runtime,'DEPENDENCIES',pending),self.assertRaises(ValueError):runtime.run(**kwargs,execute=True)
        for group,key in [('REGISTRATION_CORE',None),*(('DEPENDENCIES',k)for k in runtime.DEPENDENCIES),*(('AUXILIARIES',k)for k in runtime.AUXILIARIES)]:
            deps=deepcopy(runtime.DEPENDENCIES);deps['history_core']=(deps['history_core'][0],CORE_SHA)
            updates=dict(DEPENDENCIES=deps)
            if key:
                values=deepcopy(updates.get(group,getattr(runtime,group)));values[key]=(values[key][0],None);updates[group]=values
            else:updates[group]=(getattr(runtime,group)[0],None)
            with self.subTest(group=group,key=key),patch.multiple(runtime,**updates),patch.object(Path,'read_bytes',side_effect=AssertionError('Pending host source IO')):
                with self.assertRaises(ValueError):runtime.run(**kwargs,execute=True)

    def test_legacy_timing_uses_saved_tzif_and_cannot_upgrade_late_receipt(self):
        h=runtime.decode((runtime.ROOT/'data/cache/research/prospective_gap_history_20261009_v3/history.json').read_bytes())['history']
        tz=Path(h['tzif_reference']['path']).read_bytes()
        value=dict(session='2026-10-09',capture_started_at_utc='2026-10-09T20:01:00+00:00',capture_completed_at_utc='2026-10-09T20:01:01+00:00',writer_started_at_utc='2026-10-09T20:02:00+00:00',writer_completed_at_utc='2026-10-09T20:02:01+00:00',conservative_close_utc='2026-10-09T20:00:00+00:00',conservative_deadline_utc='2026-10-12T13:30:00+00:00',timing_classification='WITHIN_CONSERVATIVE_OBSERVATION_WINDOW')
        receipt=dict(publication_check_at_utc='2026-10-12T13:30:00+00:00',timing_classification='LATE_OBSERVATION')
        started=dict(writer_started_at_utc=value['writer_started_at_utc'])
        runtime.verify_observation_timing(value,receipt,started,tz)
        for key,replacement in [('timing_classification','WITHIN_CONSERVATIVE_OBSERVATION_WINDOW'),('publication_check_at_utc','2026-10-09T20:01:00+00:00'),('publication_check_at_utc','2026-10-12T13:30:00')]:
            bad=deepcopy(receipt);bad[key]=replacement
            with self.subTest(key=key,value=replacement),self.assertRaises(ValueError):runtime.verify_observation_timing(value,bad,started,tz)

    def test_unregistered_partial_semantic_attempt_is_not_ignored(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_compact_partial_')as folder:
            research=Path(folder)/'research';research.mkdir();partial=research/'unregistered';partial.mkdir()
            (partial/'started.json').write_bytes(runtime.encode(dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V5')))
            parent=dict(document=dict(history=dict(observations=[])))
            observation={role:dict(path=str(research/'current'/name),sha256='a'*64)for role,name in [('payload_reference','observation_payload.json'),('receipt_reference','receipt.json'),('audit_reference','independent_readback.json')]}
            with patch.object(runtime,'RESEARCH',research),self.assertRaisesRegex(ValueError,'partial or failed'):runtime.current_attempt_inventory(parent,observation,{},[])
            self.assertTrue((partial/'started.json').exists())

    def test_oversized_namespace_file_is_rejected_before_read(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_compact_resource_')as folder:
            directory=Path(folder);path=directory/'started.json'
            with path.open('wb')as stream:stream.truncate(64*1024**2+1)
            with patch.object(Path,'read_bytes',side_effect=AssertionError('Unbounded namespace read')),self.assertRaisesRegex(ValueError,'Bounded regular'):runtime.namespace(directory,('started.json',),{})

    def test_full_physical_true_v5_to_v4_actual_and_all_original_parent_edges(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_compact_v2_')as folder:
            context=physical_context(Path(folder));result=run_context(context)
            d=runtime.decode(Path(result['history_reference']['path']).read_bytes());h=d['history']
            self.assertEqual((h['typed_row_count'],h['observation_count'],h['gap_count']),(73,3,10))
            self.assertEqual(h['schema'],legacy.SCHEMA);self.assertEqual(d['actual_parent_schema'],'PROSPECTIVE_GAP_EXTENSION_HISTORY_V5')
            self.assertEqual(d['compact_adapter_schema'],runtime.ADAPTER);self.assertEqual(h['parent_references'],context[1])
            self.assertEqual(h['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
            self.assertFalse(h['observations'][-1]['month_first_actual_observation'])
            self.assertEqual(h['baseline_references'],h['accounted_baseline_references'])
            self.assertEqual({p.name for p in Path(result['history_reference']['path']).parent.iterdir()},{'started.json','history.json','publication.json'})
            for path,digest in d['source_hashes'].items():self.assertEqual(runtime.sha(Path(path).read_bytes()),digest)
            with self.assertRaises(ValueError):run_context(context)


if __name__=='__main__':unittest.main()
