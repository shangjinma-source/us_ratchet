"""Consumer-role binding tests only; no physical runtime-family execution."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from backtest import ndx_continuation_consumer_role_registry_research_v1 as registry
from backtest import ndx_compact_implementation_pair_binding_research_v1 as pair_kernel
from test_ndx_compact_implementation_pair_binding_research_v1 import arguments as pair_arguments, reference


def arguments():
    pair = pair_kernel.inspect_pair_binding(**pair_arguments())
    document = dict(schema=registry.SCHEMA, family=registry.FAMILY, protocol=registry.PROTOCOL,
        role=registry.ROLE, implementation_pair_binding_reference=deepcopy(pair['binding_reference']),
        ancestry_contract_reference=deepcopy(pair['contract_reference']),
        consumer_references={role: reference('consumer_' + role) for role in registry.CONSUMER_ROLES},
        **registry.FLAGS)
    return dict(registry=document, registry_reference=reference('consumer_registry'),
        host_registry_reference=reference('consumer_registry'), bound_pair=pair)


class ConsumerRegistryTests(unittest.TestCase):
    def test_host_pair_association_all_self_roles_detachment_no_io(self):
        for role in (None, *registry.CONSUMER_ROLES):
            value = arguments()
            if role is not None:
                value.update(self_role=role, self_reference=deepcopy(value['registry']['consumer_references'][role]))
            original = deepcopy(value)
            with patch('builtins.open', side_effect=AssertionError('Pure declaration contract')), \
                    patch('pathlib.Path.read_bytes', side_effect=AssertionError('No IO')):
                result = registry.inspect_consumer_roles(**value)
            self.assertEqual(value, original)
            self.assertEqual(result['implementation_pair_binding_reference'], value['bound_pair']['binding_reference'])
            for key in registry.FLAGS:
                self.assertIs(result[key], False)
            self.assertIs(result['consumer_schema_dispatch_selected_by_registry'], False)
            result['consumer_references'].clear()
            self.assertEqual(value, original)

    def test_artifact_cannot_select_host_registry_or_pair(self):
        for field in ('registry_reference', 'host_registry_reference'):
            value = arguments()
            value[field] = reference('unknown_registry')
            with self.subTest(field=field), self.assertRaises(ValueError):
                registry.inspect_consumer_roles(**value)
        for field in ('implementation_pair_binding_reference', 'ancestry_contract_reference'):
            value = arguments()
            value['registry'][field] = reference('unknown_' + field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                registry.inspect_consumer_roles(**value)

    def test_controlling_both_host_registry_inputs_is_not_internally_authenticated(self):
        value = arguments()
        value['registry_reference'] = reference('different_host_registry')
        value['host_registry_reference'] = deepcopy(value['registry_reference'])
        value['registry']['consumer_references']['capture_publisher'] = reference('different_host_capture_publisher')
        result = registry.inspect_consumer_roles(**value)
        self.assertEqual(result['consumer_references']['capture_publisher'], reference('different_host_capture_publisher'))
        self.assertIs(result['root_approval_authenticated'], False)
        self.assertIs(result['consumer_source_bytes_verified'], False)

    def test_closed_six_roles_and_no_schema_or_algorithm_override(self):
        for role in registry.CONSUMER_ROLES:
            value = arguments()
            del value['registry']['consumer_references'][role]
            with self.subTest(role=role), self.assertRaises(ValueError):
                registry.inspect_consumer_roles(**value)
        for key in ('schema_dispatch', 'algorithm_dependency_references', 'approved_reader', 'callback'):
            value = arguments()
            value['registry'][key] = 'UNAPPROVED_OVERRIDE'
            with self.subTest(key=key), self.assertRaises(ValueError):
                registry.inspect_consumer_roles(**value)
        value = arguments()
        value['registry']['consumer_references']['unknown_consumer'] = reference('unknown_consumer')
        with self.assertRaises(ValueError):
            registry.inspect_consumer_roles(**value)

    def test_authority_flags_are_mandatory_strict_false(self):
        for key in registry.FLAGS:
            for invalid in (True, 0, None, 'false'):
                value = arguments()
                value['registry'][key] = invalid
                with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                    registry.inspect_consumer_roles(**value)
            value = arguments()
            del value['registry'][key]
            with self.assertRaises(ValueError):
                registry.inspect_consumer_roles(**value)

    def test_roles_cannot_alias_binding_peers_algorithms_or_each_other(self):
        for special in ('registry_reference', 'host_registry_reference'):
            value = arguments()
            value['registry']['consumer_references']['capture_publisher'] = deepcopy(value[special])
            with self.subTest(special=special), self.assertRaises(ValueError):
                registry.inspect_consumer_roles(**value)
        for role in ('binding_reference', 'contract_reference', 'publisher_reference', 'independent_reader_reference'):
            value = arguments()
            value['registry']['consumer_references']['capture_publisher'] = deepcopy(value['bound_pair'][role])
            with self.subTest(role=role), self.assertRaises(ValueError):
                registry.inspect_consumer_roles(**value)
        for group in ('publisher', 'independent_reader'):
            value = arguments()
            algorithm = next(iter(value['bound_pair']['algorithm_dependency_references'][group].values()))
            value['registry']['consumer_references']['capture_publisher'] = deepcopy(algorithm)
            with self.subTest(group=group), self.assertRaises(ValueError):
                registry.inspect_consumer_roles(**value)
        for property in ('path', 'sha256'):
            value = arguments()
            consumers = value['registry']['consumer_references']
            consumers['capture_independent_reader'][property] = consumers['capture_publisher'][property]
            with self.assertRaises(ValueError):
                registry.inspect_consumer_roles(**value)

    def test_pending_aliases_and_incomplete_self_roles_rejected(self):
        for digest in (None, True, 'A' * 64, float('nan'), float('inf')):
            value = arguments()
            value['registry_reference']['sha256'] = digest
            with self.assertRaises(ValueError):
                registry.inspect_consumer_roles(**value)
        value = arguments()
        value['registry_reference']['path'] = value['registry_reference']['path'].upper()
        with self.assertRaises(ValueError):
            registry.inspect_consumer_roles(**value)
        for partial in (dict(self_role='capture_publisher'), dict(self_reference=reference('self')),
                dict(self_role='unknown', self_reference=reference('self')),
                dict(self_role='capture_publisher', self_reference=reference('wrong_self'))):
            with self.assertRaises(ValueError):
                registry.inspect_consumer_roles(**dict(arguments(), **partial))


if __name__ == '__main__':
    unittest.main()
