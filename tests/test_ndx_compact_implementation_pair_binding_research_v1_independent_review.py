"""Closed binding attacks; structural checks do not authenticate host approval."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from backtest import ndx_compact_implementation_pair_binding_research_v1 as module
from test_ndx_compact_implementation_pair_binding_research_v1 import arguments,reference


class IndependentPairBindingTests(unittest.TestCase):
    def test_artifact_cannot_select_binding_but_trusted_host_selection_is_external(self):
        value=arguments();module.inspect_pair_binding(**value)
        value['binding_reference']=reference('unknown_artifact_binding')
        with self.assertRaises(ValueError):module.inspect_pair_binding(**value)
        # The pure contract cannot prove Root approved a new independently
        # supplied host anchor. This accepted case must retain every false flag.
        value['host_binding_reference']=deepcopy(value['binding_reference'])
        result=module.inspect_pair_binding(**value)
        self.assertEqual(result['binding_reference'],reference('unknown_artifact_binding'))
        for key in module.FLAGS:self.assertIs(result[key],False)

    def test_swapped_self_roles_and_special_byte_aliases_rejected(self):
        value=arguments();module.inspect_pair_binding(**value)
        p=value['binding']['publisher_reference'];r=value['binding']['independent_reader_reference']
        value['binding']['publisher_reference'],value['binding']['independent_reader_reference']=deepcopy(r),deepcopy(p)
        with self.assertRaises(ValueError):module.inspect_pair_binding(**value)
        for field in ('publisher_reference','independent_reader_reference','contract_reference'):
            value=arguments();value['binding'][field]['sha256']=value['binding_reference']['sha256']
            if field=='publisher_reference':value['self_reference']=deepcopy(value['binding'][field])
            if field=='contract_reference':value['expected_contract_reference']=deepcopy(value['binding'][field])
            with self.subTest(role=field),self.assertRaises(ValueError):module.inspect_pair_binding(**value)

    def test_complete_role_maps_nonfinite_and_strict_reference_types(self):
        for role,field in [('publisher','publisher_dependency_references'),('independent_reader','reader_dependency_references')]:
            for bad in (None,False,0,float('nan'),float('inf')):
                value=arguments();key=next(iter(value['expected_algorithm_dependencies'][role]))
                value['expected_algorithm_dependencies'][role][key]['sha256']=bad
                value['binding'][field]=deepcopy(value['expected_algorithm_dependencies'][role])
                with self.subTest(role=role,bad=bad),self.assertRaises(ValueError):module.inspect_pair_binding(**value)
            value=arguments();value['expected_algorithm_dependencies'][role]['unknown']=reference('extra_algorithm')
            value['binding'][field]=deepcopy(value['expected_algorithm_dependencies'][role])
            with self.assertRaises(ValueError):module.inspect_pair_binding(**value)
        for bad in (False,0,float('nan'),float('inf')):
            value=arguments();value['binding']['schema']=bad
            with self.assertRaises(ValueError):module.inspect_pair_binding(**value)

    def test_flat_legacy_128_boundary_no_recursive_cycle_or_implicit_trust(self):
        value=arguments();old=[reference('old_'+str(index))for index in range(128)]
        value['approved_legacy_binding_references']=tuple(old)
        value['binding']['approved_legacy_binding_references']=deepcopy(old)
        result=module.inspect_pair_binding(**value);self.assertEqual(len(result['approved_legacy_binding_references']),128)
        value['approved_legacy_binding_references']=old+[reference('old_128')]
        value['binding']['approved_legacy_binding_references']=deepcopy(value['approved_legacy_binding_references'])
        with self.assertRaises(ValueError):module.inspect_pair_binding(**value)
        for bad in ([reference('binding')],[reference('undeclared_old')],[{'binding':reference('old')}],[[reference('old')]]):
            value=arguments();value['binding']['approved_legacy_binding_references']=deepcopy(bad)
            # No artifact may grow the host allowlist, even to a well-formed ref.
            with self.subTest(artifact=bad),self.assertRaises(ValueError):module.inspect_pair_binding(**value)
        value=arguments();cyclic=[];cyclic.append(cyclic)
        value['approved_legacy_binding_references']=cyclic;value['binding']['approved_legacy_binding_references']=cyclic
        with self.assertRaises(ValueError):module.inspect_pair_binding(**value)

    def test_predecessor_cannot_be_algorithm_or_case_alias(self):
        for kind in ('algorithm_path','algorithm_sha','case_alias','same_sha_other_path'):
            value=arguments();old=reference('old')
            if kind=='case_alias':
                values=[old,dict(path=old['path'].upper(),sha256=old['sha256'])]
            elif kind=='same_sha_other_path':values=[old,dict(path=reference('other_old')['path'],sha256=old['sha256'])]
            else:
                values=[old];dependency=value['expected_algorithm_dependencies']['publisher']['history_core']
                dependency['path'if kind=='algorithm_path'else'sha256']=old['path'if kind=='algorithm_path'else'sha256']
                value['binding']['publisher_dependency_references']=deepcopy(value['expected_algorithm_dependencies']['publisher'])
            value['approved_legacy_binding_references']=values;value['binding']['approved_legacy_binding_references']=deepcopy(values)
            with self.subTest(kind=kind),self.assertRaises(ValueError):module.inspect_pair_binding(**value)

    def test_shared_algorithm_exact_refs_detached_and_no_io(self):
        value=arguments();before=deepcopy(value)
        with patch('builtins.open',side_effect=AssertionError('No IO')),patch('pathlib.Path.read_bytes',side_effect=AssertionError('No IO')):
            result=module.inspect_pair_binding(**value)
        self.assertEqual(value,before)
        self.assertEqual(result['algorithm_dependency_references']['publisher']['parent_view'],result['algorithm_dependency_references']['independent_reader']['parent_view'])
        result['source_reference_claims'].clear();result['publisher_reference']['sha256']='f'*64
        self.assertEqual(value,before)
        self.assertNotIn('binding_reference',value['binding'])
        for field in ('source_authenticity_verified','binding_bytes_verified','peer_source_bytes_verified','root_approval_authenticated'):
            self.assertIs(result[field],False)


if __name__=='__main__':unittest.main()
