"""Pure V2 bindings; no source reads, actual registrations or output writes."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_forward_capture_runtime_registration_research_v2 as module
from test_ndx_forward_capture_runtime_registration_research_v1_independent_review import reference


def fixture():
    root='E:/Git/us_ratchet/data/cache/research'
    runtime=reference('E:/Git/us_ratchet/scripts/v5_capture_runtime.py')
    deps={role:reference('E:/Git/us_ratchet/backtest/'+role+'.py')for role in module.DEPENDENCY_ROLES}
    parent={role:reference(root+'/prior_v5/'+role+'.json')for role in module.PARENT_ROLES}
    registration=dict(schema=module.SCHEMA,runtime_reference=deepcopy(runtime),dependency_references=deepcopy(deps),
        parent=parent,output_directory=root+'/next_v5_capture',**module.FLAGS)
    return dict(registration=registration,registration_reference=reference('E:/Git/us_ratchet/contracts/v5_capture.json'),
        runtime_reference=runtime,dependency_references=deps,research_root=root)


class CaptureRegistrationV2Tests(unittest.TestCase):
    def test_detached_exact_six_dependency_plan_no_io_authority(self):
        args=fixture();before=deepcopy(args)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),patch.object(Path,'write_bytes',side_effect=AssertionError('IO')):
            result=module.prepare_forward_capture_runtime(**args)
        self.assertEqual(args,before);self.assertEqual(result['schema'],module.PLAN_SCHEMA)
        self.assertEqual(set(result['dependency_references']),set(module.DEPENDENCY_ROLES));self.assertEqual(len(result['dependency_references']),6)
        self.assertTrue(result['create_only']);self.assertTrue(result['capture_reads_host_configured_local_caches_only'])
        for key in (*module.FLAGS,'automatic_retry_allowed','registration_bytes_verified','source_bytes_verified','output_namespace_verified','parent_schema_verified'):
            self.assertIs(result[key],False)
        args['registration']['parent'].clear();args['dependency_references'].clear()
        self.assertEqual(len(result['parent']),4);self.assertEqual(len(result['dependency_references']),6)

    def test_v1_or_other_schema_rejected(self):
        for schema in ('FORWARD_CAPTURE_RUNTIME_REGISTRATION_V1','COMPACT_HISTORY_RUNTIME_REGISTRATION_V1','FORWARD_CAPTURE_RUNTIME_PLAN_V2'):
            args=fixture();args['registration']['schema']=schema
            with self.subTest(schema=schema),self.assertRaises(ValueError):module.prepare_forward_capture_runtime(**args)

    def test_host_runtime_and_each_dependency_cannot_be_reselected(self):
        for role in ('runtime_reference',*module.DEPENDENCY_ROLES):
            args=fixture()
            if role=='runtime_reference':args['registration'][role]=reference('E:/different_runtime.py','b')
            else:args['registration']['dependency_references'][role]=reference('E:/different_dependency.py','b')
            with self.subTest(role=role),self.assertRaisesRegex(ValueError,'Host'):module.prepare_forward_capture_runtime(**args)

    def test_exact_roles_nonpending_and_reference_shape(self):
        for side in ('dependency_references','parent'):
            roles=module.DEPENDENCY_ROLES if side=='dependency_references'else module.PARENT_ROLES
            for role in roles:
                for mode in ('missing','extra','pending','pointer'):
                    args=fixture();table=args['dependency_references']if side=='dependency_references'else args['registration']['parent']
                    if mode=='missing':del table[role]
                    elif mode=='extra':table['extra']=reference('E:/extra.json')
                    elif mode=='pending':table[role]['sha256']=None
                    else:table[role]['json_pointer']='/fake'
                    with self.subTest(side=side,role=role,mode=mode),self.assertRaises(ValueError):module.prepare_forward_capture_runtime(**args)

    def test_false_flags_and_extra_configuration_reject(self):
        for key in module.FLAGS:
            for value in (True,0,1,None,'False'):
                args=fixture();args['registration'][key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):module.prepare_forward_capture_runtime(**args)
        for key in ('current_cache_paths','network_url','cash','strategy','executable','execute','actual_parent_schema','trusted_host'):
            args=fixture();args['registration'][key]={}
            with self.subTest(key=key),self.assertRaises(ValueError):module.prepare_forward_capture_runtime(**args)

    def test_output_escape_alias_devices_and_input_inside_output_reject(self):
        root=fixture()['research_root']
        for output in (root,root+'/prior_v5',root+'/nested/out',root+'/../out','//server/share/out',root+'/nul',root+'/out:stream',root+'/out.',root+'/a?b'):
            args=fixture();args['registration']['output_directory']=output
            with self.subTest(output=output),self.assertRaises(ValueError):module.prepare_forward_capture_runtime(**args)
        args=fixture();args['registration_reference']=reference(args['registration']['output_directory'].upper()+'/registration.json')
        with self.assertRaises(ValueError):module.prepare_forward_capture_runtime(**args)
        args=fixture();args['registration']['parent']['reader_reference']=reference(args['runtime_reference']['path'].upper().replace('/','\\'),'b')
        with self.assertRaisesRegex(ValueError,'aliases'):module.prepare_forward_capture_runtime(**args)

    def test_same_frozen_host_accepts_distinct_future_external_registration(self):
        args=fixture();first=module.prepare_forward_capture_runtime(**args)
        args['registration_reference']=reference('E:/Git/us_ratchet/contracts/later_v5_capture.json','b')
        args['registration']['parent']={role:reference(args['research_root']+'/later_parent/'+role+'.json','c')for role in module.PARENT_ROLES}
        args['registration']['output_directory']=args['research_root']+'/later_capture_v5'
        second=module.prepare_forward_capture_runtime(**args)
        self.assertEqual(first['runtime_reference'],second['runtime_reference']);self.assertNotEqual(first['parent'],second['parent'])
        self.assertEqual(module.REFERENCE_KERNEL_SHA256,'d0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23')


if __name__=='__main__':unittest.main()
