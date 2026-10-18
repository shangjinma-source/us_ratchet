"""Synthetic bindings only: no runtime, filesystem, observations or clocks."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_gap_runtime_registration_research_v1 as module
from test_ndx_compact_history_runtime_registration_research_v1 import fixture as compact_fixture, ref


def fixture():
    args=compact_fixture();registration=args['registration'];del registration['observation']
    registration['schema']=module.SCHEMA;registration['capture']={
        role:ref('E:/Git/us_ratchet/data/cache/research/captured/'+role+'.json')for role in module.ANCHOR_ROLES}
    deps={role:ref('E:/Git/us_ratchet/backtest/'+role+'.py')for role in module.DEPENDENCY_ROLES}
    args['dependency_references']=deps;registration['dependency_references']=deepcopy(deps)
    registration.update(module.FLAGS)
    return args


class GapRegistrationTests(unittest.TestCase):
    def test_gap_contract_cannot_choose_timing_prefixes_or_old_observation_schema(self):
        for field in ('capture_started_at', 'expired_sessions', 'prefix_references',
                'accounted_prefix_evidence', 'source_bytes', 'gap_count'):
            args=fixture();args['registration'][field]={}
            with self.subTest(field=field),self.assertRaises(ValueError):
                module.prepare_gap_runtime(**args)
        args=fixture();args['registration']['schema']='PROSPECTIVE_OBSERVATION_RUNTIME_REGISTRATION_V1'
        with self.assertRaises(ValueError):module.prepare_gap_runtime(**args)

    def test_all_eight_host_roles_exact_and_no_filesystem_queries(self):
        args=fixture()
        self.assertEqual(set(module.DEPENDENCY_ROLES),{'gap_core','parent_view',
            'legacy_view','compact_helpers','prefix_core','scoped','base','capture_checker'})
        for method in ('open','stat','exists','read_bytes','iterdir'):
            with self.subTest(method=method),patch.object(Path,method,side_effect=AssertionError('Pure registration IO')):
                module.prepare_gap_runtime(**args)
        for role in module.DEPENDENCY_ROLES:
            for missing_from in ('registration','host'):
                args=fixture()
                bindings=args['registration']['dependency_references'] if missing_from=='registration' else args['dependency_references']
                del bindings[role]
                with self.subTest(role=role,missing_from=missing_from),self.assertRaises(ValueError):
                    module.prepare_gap_runtime(**args)

    def test_detached_complete_host_bound_plan_without_io(self):
        args=fixture();before=deepcopy(args)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure IO')):
            plan=module.prepare_gap_runtime(**args)
        self.assertEqual(args,before);self.assertEqual(plan['schema'],module.PLAN_SCHEMA)
        self.assertTrue(plan['create_only']);self.assertFalse(plan['automatic_retry_allowed'])
        for key in (*module.FLAGS,'source_bytes_verified','registration_bytes_verified',
                'output_namespace_verified','parent_capture_schema_verified','prefix_artifact_bytes_verified','timing_classification_verified'):
            self.assertIs(plan[key],False)
        args['registration']['capture'].clear();args['registration']['parent'].clear()
        self.assertEqual(len(plan['capture']),4);self.assertEqual(len(plan['parent']),4)

    def test_host_runtime_and_every_dependency_cannot_be_replaced(self):
        for role in ('runtime_reference',*module.DEPENDENCY_ROLES):
            args=fixture()
            item=args['registration']['runtime_reference']if role=='runtime_reference'else args['registration']['dependency_references'][role]
            item['sha256']='b'*64
            with self.subTest(role=role),self.assertRaisesRegex(ValueError,'Host'):
                module.prepare_gap_runtime(**args)

    def test_all_four_parent_capture_anchors_mandatory_nonpending(self):
        for side in ('parent','capture'):
            for role in module.ANCHOR_ROLES:
                for mode in ('missing','pending','extra'):
                    args=fixture();anchors=args['registration'][side]
                    if mode=='missing':del anchors[role]
                    elif mode=='pending':anchors[role]['sha256']=None
                    else:anchors['extra_reference']=ref('E:/extra.json')
                    with self.subTest(side=side,role=role,mode=mode),self.assertRaises(ValueError):module.prepare_gap_runtime(**args)

    def test_every_flag_requires_literal_false(self):
        for key in module.FLAGS:
            for value in (True,0,1,None,'False'):
                args=fixture();args['registration'][key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):module.prepare_gap_runtime(**args)

    def test_extra_economic_network_cache_and_execution_fields_reject(self):
        for key in ('cash','network_url','strategy_config','current_cache_paths','executable','execute','actual_parent_schema'):
            args=fixture();args['registration'][key]={}
            with self.subTest(key=key),self.assertRaises(ValueError):module.prepare_gap_runtime(**args)

    def test_outputs_cannot_escape_alias_inputs_or_use_windows_devices(self):
        paths=['E:/outside/output','E:/Git/us_ratchet/data/cache/research/parent',
            'E:/Git/us_ratchet/data/cache/research/captured','E:/Git/us_ratchet/data/cache/research/../escape',
            'E:/Git/us_ratchet/data/cache/research/nul','E:/Git/us_ratchet/data/cache/research/new:stream',
            '//server/share/output','E:/Git/us_ratchet/data/cache/research/new.']
        for path in paths:
            args=fixture();args['registration']['output_directory']=path
            with self.subTest(path=path),self.assertRaises(ValueError):module.prepare_gap_runtime(**args)

    def test_alias_conflicts_and_pending_host_or_registration_refs_reject(self):
        args=fixture();args['registration']['capture']['reader_reference']=ref(args['runtime_reference']['path'].upper(),'b')
        with self.assertRaisesRegex(ValueError,'aliases'):module.prepare_gap_runtime(**args)
        for role in ('registration_reference','runtime_reference','dependency_references'):
            args=fixture()
            if role=='dependency_references':args[role]['capture_checker']['sha256']=None
            else:args[role]['sha256']=None
            with self.subTest(role=role),self.assertRaises(ValueError):module.prepare_gap_runtime(**args)


if __name__=='__main__':unittest.main()
