"""Independent host-boundary attacks for six-dependency V5 capture registration."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_forward_capture_runtime_registration_research_v2 as core
import test_ndx_forward_capture_runtime_registration_research_v2 as author


class IndependentRegistrationV2Tests(unittest.TestCase):
    def test_conflicting_aliases_across_registration_host_and_parent_are_rejected(self):
        for target in ('runtime','dependency','parent'):
            a=author.fixture();alias=deepcopy(a['registration_reference'])
            alias['path']=alias['path'].upper().replace('/','\\');alias['sha256']='f'*64
            if target=='runtime':a['runtime_reference']=alias;a['registration']['runtime_reference']=deepcopy(alias)
            elif target=='dependency':
                a['dependency_references']['legacy_view']=alias;a['registration']['dependency_references']['legacy_view']=deepcopy(alias)
            else:a['registration']['parent']['reader_reference']=alias
            with self.subTest(target=target),self.assertRaisesRegex(ValueError,'aliases'):core.prepare_forward_capture_runtime(**a)

    def test_every_trusted_and_untrusted_reference_must_stay_outside_output(self):
        for target in ('registration','runtime',*core.DEPENDENCY_ROLES,*core.PARENT_ROLES):
            a=author.fixture();ref=dict(path=a['registration']['output_directory']+'/nested/input.json',sha256='f'*64)
            if target=='registration':a['registration_reference']=ref
            elif target=='runtime':a['runtime_reference']=ref;a['registration']['runtime_reference']=deepcopy(ref)
            elif target in core.DEPENDENCY_ROLES:
                a['dependency_references'][target]=ref;a['registration']['dependency_references'][target]=deepcopy(ref)
            else:a['registration']['parent'][target]=ref
            with self.subTest(target=target),self.assertRaisesRegex(ValueError,'aliases'):core.prepare_forward_capture_runtime(**a)

    def test_host_dependency_validation_precedes_declaration_comparison_without_io(self):
        for bad in (None,'A'*64,True,'0'*63):
            a=author.fixture();a['dependency_references']['legacy_view']['sha256']=bad
            with (self.subTest(bad=bad),patch.object(Path,'read_bytes',side_effect=AssertionError('Pure IO')),
                  self.assertRaises(ValueError)):
                core.prepare_forward_capture_runtime(**a)
        a=author.fixture();a['dependency_references'].pop('legacy_view')
        with self.assertRaises(ValueError):core.prepare_forward_capture_runtime(**a)

    def test_future_run_bindings_are_detached_and_never_authenticate_parent_schema(self):
        a=author.fixture();before=deepcopy(a)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure IO')):plan=core.prepare_forward_capture_runtime(**a)
        self.assertEqual(a,before);self.assertIs(plan['parent_schema_verified'],False)
        self.assertIs(plan['registration_bytes_verified'],False);self.assertIs(plan['source_bytes_verified'],False)
        self.assertEqual(set(plan['dependency_references']),set(core.DEPENDENCY_ROLES))
        self.assertEqual(len(plan['source_reference_claims']),12)
        plan['parent']['reference']['sha256']='f'*64
        self.assertEqual(a,before)


if __name__=='__main__':unittest.main()
