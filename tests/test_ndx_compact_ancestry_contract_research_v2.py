"""Pure mixed-role planning; no physical consumer acceptance is claimed."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from backtest import ndx_compact_ancestry_contract_research_v1 as old
from backtest import ndx_compact_ancestry_contract_research_v2 as graph
from backtest import ndx_continuation_consumer_metadata_research_v1 as metadata
from backtest import ndx_continuation_consumer_role_registry_research_v1 as registry
from test_ndx_continuation_consumer_role_registry_research_v1 import arguments
from test_ndx_compact_implementation_pair_binding_research_v1 import reference
from test_ndx_compact_ancestry_contract_research_v1 import graph as legacy_graph, envelope


def context():
    values = arguments()
    core = reference('consumer_core')
    core['sha256'] = metadata.CONSUMER_REGISTRY_KERNEL_SHA256
    return dict(bound_pair=values['bound_pair'],
        consumer_registry_view=registry.inspect_consumer_roles(**values),
        consumer_registry_core_reference=core,
        metadata_contract_reference=reference('metadata_core'))


def four(node):
    return {role: deepcopy(node[role]) for role in graph.PARENT_ROLES}


def node(name, prior, host, gap=False, provenance=False):
    value = envelope(name, graph.GAP_SCHEMA if gap else graph.ACTUAL_SCHEMA, four(prior))
    pair = host['bound_pair']
    inputs = value['document']['input_references']
    if gap:
        dependencies = {role: reference('gap_algorithm_' + role)
            for role in metadata.REGISTERED_DEPENDENCY_ROLES['gap_publisher']}
        inputs.update(runtime=deepcopy(host['consumer_registry_view']['consumer_references']['gap_publisher']),
            dependencies=dependencies, **metadata.continuation_input_references(
                registered_dependency_references=dependencies, consumer_role='gap_publisher', **host))
        value['reader_reference'] = deepcopy(host['consumer_registry_view']['consumer_references']['gap_independent_reader'])
    else:
        inputs.update(runtime=deepcopy(pair['publisher_reference']),
            dependencies=deepcopy(pair['algorithm_dependency_references']['publisher']))
        value['reader_reference'] = deepcopy(pair['independent_reader_reference'])
    for field in ('document', 'publication', 'readback'):
        value[field]['input_references'] = deepcopy(inputs)
        if gap:
            role = 'gap_independent_reader' if field == 'readback' else 'gap_publisher'
            value[field].update(metadata.expected_consumer_metadata(consumer_role=role, **host))
        else:
            value[field].update(implementation_pair_binding_reference=deepcopy(pair['binding_reference']),
                ancestry_contract_reference=deepcopy(pair['contract_reference']))
            if provenance:
                header = metadata.expected_consumer_metadata(consumer_role='gap_publisher', **host)
                for key in ('consumer_role_registry_reference', 'consumer_registry_core_reference',
                        'consumer_metadata_contract_reference'):
                    value[field][key] = deepcopy(header[key])
                value[field]['input_references'].update(
                    consumer_role_registry=deepcopy(header['consumer_role_registry_reference']),
                    consumer_registry_core=deepcopy(header['consumer_registry_core_reference']),
                    consumer_metadata_contract=deepcopy(header['consumer_metadata_contract_reference']))
    value['readback']['reader_sha256'] = value['reader_reference']['sha256']
    return value


class ConsumerGraphTests(unittest.TestCase):
    def test_mixed_legacy_actual_continuation_gap_oldest_first_no_io(self):
        host = context()
        nodes, _, legacy = legacy_graph(3)
        nodes.append(node('current13', nodes[-1], host, provenance=True))
        nodes.append(node('gap14', nodes[-1], host, gap=True))
        dependencies = nodes[-1]['document']['input_references']['dependencies']
        nodes.append(node('current15', nodes[-1], host, provenance=True))
        lookup = {(item['reference']['path'], item['reference']['sha256']): item for item in nodes}
        original = deepcopy((nodes, host))
        with patch('builtins.open', side_effect=AssertionError('No graph IO')), \
                patch('pathlib.Path.read_bytes', side_effect=AssertionError('No graph bytes')):
            result = graph.inspect_ancestry_graph(four(nodes[-1]), lookup, legacy_implementations=legacy,
                registered_gap_dependency_references=dependencies, **host)
        self.assertEqual([item['kind'] for item in result['work_items']],
            ['terminal', 'actual', 'gap', 'actual', 'gap', 'actual'])
        self.assertEqual(result['work_items'][-2]['implementation_role'], 'HOST_BOUND_CONTINUATION_GAP_PAIR')
        self.assertEqual(result['work_items'][-1]['implementation_role'], 'HOST_BOUND_CURRENT_PAIR')
        self.assertFalse(result['file_bytes_read'])
        self.assertEqual((nodes, host), original)
        result['work_items'][0]['child_references'].clear()
        self.assertEqual((nodes, host), original)

    def test_gap_unknown_header_runtime_reader_and_algorithms_fail(self):
        host = context()
        bases, _, legacy = legacy_graph(1)
        value = node('new_gap', bases[-1], host, gap=True)
        dependencies = deepcopy(value['document']['input_references']['dependencies'])
        for field in metadata.METADATA_KEYS:
            changed = deepcopy(value)
            del changed['readback'][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                graph.classify_parent_edge(changed, registered_gap_dependency_references=dependencies, **host)
        for key in ('runtime', 'dependencies', 'consumer_role_registry'):
            changed = deepcopy(value)
            for field in ('document', 'publication', 'readback'):
                changed[field]['input_references'][key] = reference('unknown')
            with self.subTest(key=key), self.assertRaises(ValueError):
                graph.classify_parent_edge(changed, registered_gap_dependency_references=dependencies, **host)
        changed = deepcopy(value)
        changed['reader_reference'] = reference('foreign_gap_reader')
        changed['readback']['reader_sha256'] = changed['reader_reference']['sha256']
        with self.assertRaises(ValueError):
            graph.classify_parent_edge(changed, registered_gap_dependency_references=dependencies, **host)
        with self.assertRaises(ValueError):
            old.classify_parent_edge(value, bound_pair=host['bound_pair'], legacy_implementations=legacy)

    def test_actual_consumer_provenance_cannot_change_its_role_or_be_partial(self):
        host = context()
        bases, _, _ = legacy_graph(1)
        value = node('new_actual', bases[-1], host, provenance=True)
        self.assertEqual(graph.classify_parent_edge(value, **host)['kind'], 'actual')
        changed = deepcopy(value)
        del changed['publication']['consumer_role_registry_reference']
        with self.assertRaises(ValueError):
            graph.classify_parent_edge(changed, **host)
        changed = deepcopy(value)
        for field in ('document', 'publication', 'readback'):
            changed[field]['input_references']['consumer_role_registry'] = reference('wrong_C')
        with self.assertRaises(ValueError):
            graph.classify_parent_edge(changed, **host)
        changed = deepcopy(value)
        changed['document']['consumer_role'] = 'gap_publisher'
        with self.assertRaises(ValueError):
            graph.classify_parent_edge(changed, **host)

    def test_global_cycle_and_budget_span_new_gap_and_actual(self):
        host = context()
        bases, _, legacy = legacy_graph(1)
        values = [bases[0]]
        for index in range(1, graph.MAX_PARENT_NODES + 1):
            values.append(node('depth_' + str(index), values[-1], host, gap=index % 2 == 0, provenance=True))
        lookup = {(item['reference']['path'], item['reference']['sha256']): item for item in values}
        dependencies = values[2]['document']['input_references']['dependencies']
        with self.assertRaisesRegex(ValueError, 'Global actual/gap cycle or depth'):
            graph.inspect_ancestry_graph(four(values[-1]), lookup, legacy_implementations=legacy,
                registered_gap_dependency_references=dependencies, **host)
        value = deepcopy(values[2])
        for field in ('document', 'publication', 'readback'):
            value[field]['input_references']['parent'] = four(value)
        value['document']['history']['parent_references'] = four(value)
        lookup = {(value['reference']['path'], value['reference']['sha256']): value}
        with self.assertRaisesRegex(ValueError, 'Global actual/gap cycle or depth'):
            graph.inspect_ancestry_graph(four(value), lookup,
                registered_gap_dependency_references=dependencies, **host)


if __name__ == '__main__':
    unittest.main()
