"""Independent closed consumer-role declaration attacks; never authenticate IO."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from backtest import ndx_continuation_consumer_role_registry_research_v1 as module
from test_ndx_continuation_consumer_role_registry_research_v1 import arguments,reference


class IndependentConsumerRoleTests(unittest.TestCase):
    def test_unknown_registry_pair_contract_and_external_host_limit(self):
        baseline=arguments();module.inspect_consumer_roles(**baseline)
        for field in ('registry_reference','implementation_pair_binding_reference','ancestry_contract_reference'):
            value=arguments()
            if field=='registry_reference':value[field]=reference('unapproved_C')
            else:value['registry'][field]=reference('unapproved_'+field)
            with self.subTest(field=field),self.assertRaises(ValueError):module.inspect_consumer_roles(**value)
        value=arguments();value['host_registry_reference']=reference('host_selected_new_C');value['registry_reference']=deepcopy(value['host_registry_reference'])
        value['registry']['consumer_references']['observation_writer']=reference('host_selected_new_writer')
        result=module.inspect_consumer_roles(**value)
        self.assertEqual(result['consumer_references']['observation_writer'],reference('host_selected_new_writer'))
        for key in module.FLAGS:self.assertIs(result[key],False)

    def test_each_consumer_self_role_cannot_be_exchanged_with_another(self):
        for role in module.CONSUMER_ROLES:
            for other in module.CONSUMER_ROLES:
                if role==other:continue
                value=arguments();consumers=value['registry']['consumer_references']
                value.update(self_role=role,self_reference=deepcopy(consumers[role]))
                module.inspect_consumer_roles(**value)
                consumers[role],consumers[other]=deepcopy(consumers[other]),deepcopy(consumers[role])
                with self.subTest(role=role,other=other),self.assertRaises(ValueError):module.inspect_consumer_roles(**value)

    def test_path_and_byte_aliases_for_special_and_algorithm_roles_fail(self):
        for name in ('binding_reference','contract_reference','publisher_reference','independent_reader_reference'):
            for key in ('path','sha256'):
                value=arguments();value['registry']['consumer_references']['gap_publisher'][key]=value['bound_pair'][name][key]
                with self.subTest(special=name,key=key),self.assertRaises(ValueError):module.inspect_consumer_roles(**value)
        for group in ('publisher','independent_reader'):
            for algorithm in arguments()['bound_pair']['algorithm_dependency_references'][group]:
                for key in ('path','sha256'):
                    value=arguments();value['registry']['consumer_references']['capture_publisher'][key]=value['bound_pair']['algorithm_dependency_references'][group][algorithm][key]
                    with self.subTest(group=group,algorithm=algorithm,key=key),self.assertRaises(ValueError):module.inspect_consumer_roles(**value)
        value=arguments();consumers=value['registry']['consumer_references']
        consumers['gap_independent_reader']=dict(path=consumers['gap_publisher']['path'].upper(),sha256=consumers['gap_publisher']['sha256'])
        with self.assertRaises(ValueError):module.inspect_consumer_roles(**value)

    def test_closed_schema_nonfinite_false_and_invalid_view_identity(self):
        for key in module.FLAGS:
            for invalid in (0,1,float('nan'),float('inf')):
                value=arguments();value['registry'][key]=invalid
                with self.subTest(flag=key,invalid=invalid),self.assertRaises(ValueError):module.inspect_consumer_roles(**value)
        for key in ('schema','family','protocol'):
            value=arguments();value['bound_pair'][key]='unknown_view_identity'
            with self.subTest(viewkey=key),self.assertRaises(ValueError):module.inspect_consumer_roles(**value)
        for key in ('algorithm_dependencies','callback','approved_legacy_registry_references','actual_parent_schema'):
            value=arguments();value['registry'][key]={}
            with self.subTest(extrakey=key),self.assertRaises(ValueError):module.inspect_consumer_roles(**value)
        for bad in (False,0,None,float('nan'),float('inf')):
            value=arguments();value['registry']['consumer_references']['capture_publisher']['sha256']=bad
            with self.assertRaises(ValueError):module.inspect_consumer_roles(**value)

    def test_optional_self_is_complete_and_result_is_pure_detached(self):
        for bad in (False,0,[],{},'publisher'):
            value=arguments();value.update(self_role=bad,self_reference=reference('self'))
            with self.subTest(role=bad),self.assertRaises(ValueError):module.inspect_consumer_roles(**value)
        value=arguments();before=deepcopy(value)
        with patch('builtins.open',side_effect=AssertionError('No IO')),patch('pathlib.Path.read_bytes',side_effect=AssertionError('No IO')):
            result=module.inspect_consumer_roles(**value)
        self.assertEqual(value,before)
        result['source_reference_claims'].clear();result['consumer_references']['gap_publisher']['sha256']='f'*64
        self.assertEqual(value,before)
        self.assertIs(result['append_algorithm_called'],False);self.assertIs(result['consumer_schema_dispatch_selected_by_registry'],False)


if __name__=='__main__':unittest.main()
