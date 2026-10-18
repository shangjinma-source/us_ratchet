"""Independent registration attacks; supplied host bindings are not IO proof."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_compact_history_runtime_registration_research_v1 as core
from test_ndx_compact_history_runtime_registration_research_v1 import fixture,ref


class RegistrationIndependentReviewTests(unittest.TestCase):
    def test_registration_cannot_retarget_runtime_path_or_dependency_roles(self):
        for mode in ('runtime_path','dependency_path','dependency_role','extra_host_role'):
            a=fixture()
            if mode=='runtime_path':a['registration']['runtime_reference']['path']='E:/arbitrary/runtime.py'
            elif mode=='dependency_path':a['registration']['dependency_references']['history_core']['path']='E:/other.py'
            elif mode=='dependency_role':a['registration']['dependency_references']['history_core']=deepcopy(a['registration']['dependency_references']['compact_helpers'])
            else:a['dependency_references']['new_role']=ref('E:/extra.py')
            with self.subTest(mode=mode),self.assertRaises(ValueError):core.prepare_compact_history_runtime(**a)

    def test_alias_conflicts_across_registration_host_and_parent(self):
        for role in ('reference','publication_reference','readback_reference','reader_reference'):
            a=fixture();target=a['runtime_reference']['path']
            a['registration']['parent'][role]=ref(target.upper().replace('/','\\'),'b')
            with self.subTest(role=role),self.assertRaisesRegex(ValueError,'Conflicting path aliases'):
                core.prepare_compact_history_runtime(**a)
        a=fixture();a['registration_reference']=ref(a['runtime_reference']['path'].upper(),'b')
        with self.assertRaises(ValueError):core.prepare_compact_history_runtime(**a)

    def test_input_namespace_output_alias_and_nested_escape(self):
        for kind in ('case_slash','self_input','ancestor_input','registration_inside'):
            a=fixture();output=a['registration']['output_directory']
            if kind=='case_slash':a['registration']['output_directory']=a['research_root']+'\\actual'
            elif kind=='self_input':a['registration']['observation']['payload_reference']=ref(output.upper())
            elif kind=='ancestor_input':a['registration']['parent']['reference']=ref(output.upper()+'/HISTORY.JSON')
            else:a['registration_reference']=ref(output+'/registration.json')
            with self.subTest(kind=kind),self.assertRaises(ValueError):core.prepare_compact_history_runtime(**a)

    def test_pending_refs_all_roles_and_host_refs_reject(self):
        for namespace,roles in [('parent',core.ANCHOR_ROLES),('observation',core.OBSERVATION_ROLES)]:
            for role in roles:
                a=fixture();a['registration'][namespace][role]['sha256']=None
                with self.subTest(namespace=namespace,role=role),self.assertRaises(ValueError):core.prepare_compact_history_runtime(**a)
        for key in ('registration_reference','runtime_reference'):
            a=fixture();a[key]['sha256']='A'*64
            with self.assertRaises(ValueError):core.prepare_compact_history_runtime(**a)

    def test_device_unc_dot_ads_special_paths_reject_every_reference(self):
        bad=['E:relative','\\\\?\\E:\\absolute','\\\\server\\share\\file',
             'E:/folder/./file','E:/folder/../file','E:/folder/file:ads',
             'E:/folder/file.','E:/folder/file /child','E:/folder/nul.json',
             'E:/folder/lpt9.log','E:/folder/a\x00b','E:/folder/a|b']
        for path in bad:
            a=fixture();a['registration']['observation']['audit_reference']=ref(path)
            with self.subTest(path=path),self.assertRaises(ValueError):core.prepare_compact_history_runtime(**a)

    def test_all_authority_flags_strict_false_and_unknown_fields_reject(self):
        for key in core.FLAGS:
            for value in (0,1,None,'false'):
                a=fixture();a['registration'][key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):core.prepare_compact_history_runtime(**a)
        a=fixture();a['registration']['trusted_host_configuration']=True
        with self.assertRaises(ValueError):core.prepare_compact_history_runtime(**a)

    def test_host_configuration_is_explicit_external_trust_not_self_authentication(self):
        a=fixture();a['runtime_reference']=ref('E:/host_reviewed/another_runtime.py','c')
        a['registration']['runtime_reference']=deepcopy(a['runtime_reference'])
        with (patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),
              patch.object(Path,'write_bytes',side_effect=AssertionError('IO'))):
            plan=core.prepare_compact_history_runtime(**a)
        self.assertFalse(plan['source_bytes_verified']);self.assertFalse(plan['registration_bytes_verified'])
        self.assertEqual(plan['runtime_reference'],a['runtime_reference'])

    def test_repeated_frozen_runtime_runs_detached_and_no_namespace_authority(self):
        a=fixture();before=deepcopy(a);plan=core.prepare_compact_history_runtime(**a)
        self.assertEqual(a,before);self.assertTrue(plan['create_only']);self.assertFalse(plan['output_namespace_verified'])
        a['registration']['output_directory']=a['research_root']+'/different_run_v1'
        later=core.prepare_compact_history_runtime(**a)
        self.assertEqual(plan['runtime_reference'],later['runtime_reference'])
        self.assertNotEqual(plan['output_directory'],later['output_directory'])


if __name__=='__main__':unittest.main()
