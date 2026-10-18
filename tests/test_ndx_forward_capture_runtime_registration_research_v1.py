from copy import deepcopy
import unittest
from backtest import ndx_forward_capture_runtime_registration_research_v1 as module
from test_ndx_compact_history_runtime_registration_research_v1 import fixture as compact_fixture,ref


def fixture():
    args=compact_fixture();registration=args['registration'];del registration['observation']
    registration['schema']=module.SCHEMA
    dependencies={role:ref('E:/Git/us_ratchet/backtest/'+role+'.py')for role in module.DEPENDENCY_ROLES}
    args['dependency_references']=dependencies;registration['dependency_references']=deepcopy(dependencies)
    registration.update(module.FLAGS)
    return args


class CaptureRegistrationTests(unittest.TestCase):
    def test_complete_plan_no_io_authority_and_detached(self):
        args=fixture();plan=module.prepare_forward_capture_runtime(**args)
        self.assertTrue(plan['create_only']);self.assertTrue(plan['capture_reads_host_configured_local_caches_only'])
        for flag in module.FLAGS:self.assertIs(plan[flag],False)
        self.assertFalse(plan['source_bytes_verified']);self.assertFalse(plan['automatic_retry_allowed'])
        args['registration']['parent'].clear();self.assertEqual(len(plan['parent']),4)

    def test_runtime_dependency_and_pending_parent_must_bind(self):
        for kind in ['runtime','dependency','parent_pending','parent_missing']:
            with self.subTest(kind=kind):
                args=fixture();registration=args['registration']
                if kind=='runtime':registration['runtime_reference']['sha256']='b'*64
                elif kind=='dependency':registration['dependency_references']['capture_core']['sha256']='b'*64
                elif kind=='parent_pending':registration['parent']['readback_reference']['sha256']=None
                else:del registration['parent']['readback_reference']
                with self.assertRaises(ValueError):module.prepare_forward_capture_runtime(**args)

    def test_registration_cannot_request_network_live_or_custom_cache(self):
        for field,value in [('network_capture_performed',True),('live_mutation_allowed',True),
            ('future_independent_oos',0),('current_cache_paths',{'QQQ':'E:/different.csv'})]:
            args=fixture();args['registration'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):module.prepare_forward_capture_runtime(**args)

    def test_output_and_source_alias_reject(self):
        for path in ['E:/outside/output','E:/Git/us_ratchet/data/cache/research/parent',
            'E:/Git/us_ratchet/data/cache/research/../escape','E:/Git/us_ratchet/data/cache/research/nul']:
            args=fixture();args['registration']['output_directory']=path
            with self.subTest(path=path),self.assertRaises(ValueError):module.prepare_forward_capture_runtime(**args)
        args=fixture();args['registration']['parent']['reader_reference']=ref(args['runtime_reference']['path'].upper(),'b')
        with self.assertRaises(ValueError):module.prepare_forward_capture_runtime(**args)


if __name__=='__main__':unittest.main()
