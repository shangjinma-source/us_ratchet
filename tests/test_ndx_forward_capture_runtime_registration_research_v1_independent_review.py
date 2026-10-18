"""Independent capture-registration structural attacks, no capture or output IO."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_forward_capture_runtime_registration_research_v1 as core


def reference(path,digit='a'):return dict(path=path,sha256=digit*64)


def fixture():
    runtime=reference('E:/Git/us_ratchet/scripts/registered_capture_runtime.py')
    dependencies={role:reference('E:/Git/us_ratchet/backtest/'+role+'.py')for role in core.DEPENDENCY_ROLES}
    parent={role:reference('E:/Git/us_ratchet/data/cache/research/prior/'+role+'.json')for role in core.PARENT_ROLES}
    root='E:/Git/us_ratchet/data/cache/research'
    registration=dict(schema=core.SCHEMA,runtime_reference=deepcopy(runtime),dependency_references=deepcopy(dependencies),
        parent=parent,output_directory=root+'/next_capture_v1',**core.FLAGS)
    return dict(registration=registration,registration_reference=reference('E:/Git/us_ratchet/research_contracts/capture_run.json'),
        runtime_reference=runtime,dependency_references=dependencies,research_root=root)


class ForwardCaptureRegistrationReview(unittest.TestCase):
    def test_host_binding_cannot_be_reselected_by_registration(self):
        for key in ('runtime_reference',*core.DEPENDENCY_ROLES):
            a=fixture()
            if key=='runtime_reference':a['registration'][key]=reference('E:/malicious.py','b')
            else:a['registration']['dependency_references'][key]=reference('E:/malicious.py','b')
            with self.subTest(key=key),self.assertRaises(ValueError):core.prepare_forward_capture_runtime(**a)

    def test_exact_five_dependency_roles_and_four_parent_roles(self):
        for mode in ('missing_dependency','extra_dependency','missing_parent','extra_parent','pending_parent'):
            a=fixture()
            if mode=='missing_dependency':del a['dependency_references']['base']
            elif mode=='extra_dependency':a['dependency_references']['new']=reference('E:/new.py')
            elif mode=='missing_parent':del a['registration']['parent']['readback_reference']
            elif mode=='extra_parent':a['registration']['parent']['fake']=reference('E:/new.json')
            else:a['registration']['parent']['reference']['sha256']=None
            with self.subTest(mode=mode),self.assertRaises(ValueError):core.prepare_forward_capture_runtime(**a)

    def test_cannot_configure_cache_network_cash_strategy_or_execute(self):
        for key in ('source_references','current','network_url','executable','cash','strategy','observation','execute','trusted_host'):
            a=fixture();a['registration'][key]={'QQQ':'http://untrusted','SPY':'E:/mutable.csv'}
            with self.subTest(key=key),self.assertRaises(ValueError):core.prepare_forward_capture_runtime(**a)
        a=fixture();a['registration']['schema']='COMPACT_HISTORY_RUNTIME_REGISTRATION_V1'
        with self.assertRaises(ValueError):core.prepare_forward_capture_runtime(**a)

    def test_all_false_permissions_strictly_false(self):
        for key in core.FLAGS:
            for value in (True,0,None):
                a=fixture();a['registration'][key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):core.prepare_forward_capture_runtime(**a)

    def test_output_aliases_and_path_escapes_reject(self):
        a=fixture();root=a['research_root']
        for output in (root,root+'/prior',root+'/../escape',root+'/nested/next','//server/share/out',
                       root+'/nul',root+'/out:stream',root+'/out.',root+'/CON.txt',root+'/a?b'):
            a=fixture();a['registration']['output_directory']=output
            with self.subTest(output=output),self.assertRaises(ValueError):core.prepare_forward_capture_runtime(**a)
        a=fixture();a['registration_reference']=reference(a['registration']['output_directory'].upper()+'/registration.json')
        with self.assertRaises(ValueError):core.prepare_forward_capture_runtime(**a)

    def test_alias_conflicting_digest_across_all_roles(self):
        for role in core.PARENT_ROLES:
            a=fixture();a['registration']['parent'][role]=reference(a['runtime_reference']['path'].upper().replace('/','\\'),'b')
            with self.subTest(role=role),self.assertRaisesRegex(ValueError,'Conflicting path aliases'):
                core.prepare_forward_capture_runtime(**a)

    def test_no_io_detached_plan_and_explicit_scope(self):
        a=fixture();before=deepcopy(a)
        with (patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),
              patch.object(Path,'write_bytes',side_effect=AssertionError('IO'))):plan=core.prepare_forward_capture_runtime(**a)
        self.assertEqual(a,before);self.assertTrue(plan['create_only']);self.assertTrue(plan['capture_reads_host_configured_local_caches_only'])
        for key in ('automatic_retry_allowed','registration_bytes_verified','source_bytes_verified','output_namespace_verified'):self.assertFalse(plan[key])
        a['registration']['parent']['reference']['path']='changed';self.assertNotEqual(plan['parent']['reference']['path'],'changed')

    def test_frozen_runtime_supports_distinct_later_registration_without_hot_edit(self):
        a=fixture();one=core.prepare_forward_capture_runtime(**a)
        a['registration_reference']=reference('E:/Git/us_ratchet/research_contracts/later.json','b')
        a['registration']['parent']={role:reference('E:/Git/us_ratchet/data/cache/research/later/'+role+'.json','c')for role in core.PARENT_ROLES}
        a['registration']['output_directory']=a['research_root']+'/later_capture_v1'
        two=core.prepare_forward_capture_runtime(**a)
        self.assertEqual(one['runtime_reference'],two['runtime_reference']);self.assertNotEqual(one['parent'],two['parent'])
        self.assertEqual(core.REFERENCE_KERNEL_SHA256,'d0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23')


if __name__=='__main__':unittest.main()
