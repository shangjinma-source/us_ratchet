"""Integrate frozen declaration contracts; this is not physical actual IO."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_compact_ancestry_contract_research_v1 as graph
from backtest import ndx_compact_implementation_pair_binding_research_v1 as binding
from scripts import ndx_prospective_observation_writer_v3_20261009 as legacy_writer
from test_ndx_compact_implementation_pair_binding_research_v1 import arguments, reference


def actual(name, prior, pair):
    refs = {role: reference(name + '_' + role) for role in graph.PARENT_ROLES}
    refs['reader_reference'] = deepcopy(pair['independent_reader_reference'])
    observation = {role: reference(name + '_observation_' + role) for role in graph.OBSERVATION_ROLES}
    inputs = dict(parent=deepcopy(prior), observation=observation,
        runtime=deepcopy(pair['publisher_reference']),
        dependencies=deepcopy(pair['algorithm_dependency_references']['publisher']))
    metadata = dict(implementation_pair_binding_reference=deepcopy(pair['binding_reference']),
        ancestry_contract_reference=deepcopy(pair['contract_reference']))
    document = dict(history=dict(schema=graph.ACTUAL_SCHEMA, parent_references=deepcopy(prior),
        observation_references=deepcopy(observation)), input_references=deepcopy(inputs), **metadata)
    publication = dict(history_reference=deepcopy(refs['reference']), input_references=deepcopy(inputs), **metadata)
    readback = dict(history_reference=deepcopy(refs['reference']), publication_reference=deepcopy(refs['publication_reference']),
        reader_sha256=refs['reader_reference']['sha256'], input_references=deepcopy(inputs), **metadata)
    return dict(refs, document=document, publication=publication, readback=readback)


def four(node):
    return {role: deepcopy(node[role]) for role in graph.PARENT_ROLES}


def fixed_terminal():
    node = deepcopy(legacy_writer.PARENT_BOUND)
    for field, role in (('document', 'reference'), ('publication', 'publication_reference'), ('readback', 'readback_reference')):
        raw = Path(node[role]['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != node[role]['sha256']:
            raise ValueError('Fixed V3 bytes changed')
        node[field] = json.loads(raw)
    legacy = [dict(parent_schema=graph.TERMINAL_SCHEMA, input_role='pure',
        implementation_reference=deepcopy(node['document']['input_references']['pure']),
        reader_reference=deepcopy(node['reader_reference']), terminal_reference=deepcopy(node['reference']))]
    return node, legacy


class PairGraphIntegrationTests(unittest.TestCase):
    def test_real_terminal_and_both_self_roles_have_identical_detached_graph_plans(self):
        values = arguments()
        publisher = binding.inspect_pair_binding(**values)
        values.update(self_role='independent_reader', self_reference=values['binding']['independent_reader_reference'])
        reader = binding.inspect_pair_binding(**values)
        base, legacy = fixed_terminal()
        nodes = [base]
        for name in ('declared13', 'declared14', 'declared15'):
            nodes.append(actual(name, four(nodes[-1]), publisher))
        envelopes = {(node['reference']['path'], node['reference']['sha256']): node for node in nodes}
        with patch('builtins.open', side_effect=AssertionError('Contracts cannot read files')), \
                patch('pathlib.Path.read_bytes', side_effect=AssertionError('No graph IO')):
            first = graph.inspect_ancestry_graph(four(nodes[-1]), envelopes,
                bound_pair=publisher, legacy_implementations=legacy)
            second = graph.inspect_ancestry_graph(four(nodes[-1]), envelopes,
                bound_pair=reader, legacy_implementations=legacy)
        self.assertEqual(first, second)
        self.assertEqual(first['parent_node_count'], 4)
        self.assertEqual([item['kind'] for item in first['work_items']], ['terminal', 'actual', 'actual', 'actual'])
        self.assertTrue(all(item['whole_history_arithmetic_replay_required'] for item in first['work_items'][1:]))
        self.assertFalse(first['append_algorithm_called'])
        self.assertFalse(first['file_bytes_read'])

    def test_allowlisted_binding_ref_does_not_grant_an_unknown_pair_role(self):
        values = arguments()
        old_ref = reference('old_binding')
        values['approved_legacy_binding_references'] = [old_ref]
        values['binding']['approved_legacy_binding_references'] = [deepcopy(old_ref)]
        pair = binding.inspect_pair_binding(**values)
        base, legacy = fixed_terminal()
        node = actual('unverified_old_pair', four(base), pair)
        for field in ('document', 'publication', 'readback'):
            node[field]['implementation_pair_binding_reference'] = deepcopy(old_ref)
        with self.assertRaisesRegex(ValueError, 'Artifact binding'):
            graph.classify_parent_edge(node, bound_pair=pair, legacy_implementations=legacy)

    def test_coordinated_untrusted_pair_cannot_override_independent_host_selection(self):
        values = arguments()
        expected = binding.inspect_pair_binding(**values)
        base, legacy = fixed_terminal()
        node = actual('coordinated_foreign', four(base), expected)
        attacker = deepcopy(values)
        attacker['binding_reference'] = reference('foreign_binding')
        attacker['binding']['publisher_reference'] = reference('foreign_publisher')
        attacker['binding']['independent_reader_reference'] = reference('foreign_reader')
        attacker['self_reference'] = reference('foreign_publisher')
        with self.assertRaisesRegex(ValueError, 'Independently selected'):
            binding.inspect_pair_binding(**attacker)
        for field in ('document', 'publication', 'readback'):
            node[field]['implementation_pair_binding_reference'] = deepcopy(attacker['binding_reference'])
            node[field]['input_references']['runtime'] = deepcopy(attacker['self_reference'])
        node['reader_reference'] = deepcopy(attacker['binding']['independent_reader_reference'])
        node['readback']['reader_sha256'] = node['reader_reference']['sha256']
        with self.assertRaisesRegex(ValueError, 'Artifact binding'):
            graph.classify_parent_edge(node, bound_pair=expected, legacy_implementations=legacy)


if __name__ == '__main__':
    unittest.main()
