"""Structural graph tests only; no claim of physical continuation or byte IO."""
from copy import deepcopy
import unittest
from backtest import ndx_compact_ancestry_contract_research_v1 as contract


def ref(name):
    return {'path': 'E:/graph/' + name, 'sha256': 'a' * 64}


def refs(name, observation=False):
    roles = contract.OBSERVATION_ROLES if observation else contract.PARENT_ROLES
    return {role: ref(name + '/' + role) for role in roles}


def pair():
    return dict(binding_reference=ref('binding'), contract_reference=ref('contract'),
        publisher_reference=ref('publisher'), independent_reader_reference=ref('reader'),
        algorithm_dependency_references={'publisher': {'history_core': ref('append')},
            'independent_reader': {'formula': ref('independent')}})


def envelope(name, schema, prior=None, modern=False):
    current = refs(name)
    inputs = {'runtime': ref('legacy_publisher')}
    history = {'schema': schema}
    if prior:
        history['parent_references'] = deepcopy(prior)
        inputs['parent'] = deepcopy(prior)
    if schema == contract.ACTUAL_SCHEMA:
        history['observation_references'] = refs(name + '_obs', observation=True)
        inputs['observation'] = deepcopy(history['observation_references'])
    if schema == contract.GAP_SCHEMA:
        history['capture_references'] = refs(name + '_capture')
        inputs['capture'] = deepcopy(history['capture_references'])
    if modern:
        current['reader_reference'] = pair()['independent_reader_reference']
        inputs['runtime'] = pair()['publisher_reference']
        inputs['dependencies'] = pair()['algorithm_dependency_references']['publisher']
    document = dict(history=history, input_references=deepcopy(inputs))
    publication = dict(history_reference=current['reference'], input_references=deepcopy(inputs))
    readback = dict(history_reference=current['reference'], publication_reference=current['publication_reference'],
        reader_sha256=current['reader_reference']['sha256'], input_references=deepcopy(inputs))
    if modern:
        for value in (document, publication, readback):
            value.update(implementation_pair_binding_reference=pair()['binding_reference'],
                ancestry_contract_reference=pair()['contract_reference'])
    return dict(current, document=document, publication=publication, readback=readback)


def graph(size=4):
    base = envelope('0', contract.TERMINAL_SCHEMA)
    nodes = [base]
    for index in range(1, size):
        schema = contract.ACTUAL_SCHEMA if index % 2 else contract.GAP_SCHEMA
        nodes.append(envelope(str(index), schema, {role: nodes[-1][role] for role in contract.PARENT_ROLES}))
    legacy = []
    for schema in (contract.TERMINAL_SCHEMA, contract.ACTUAL_SCHEMA, contract.GAP_SCHEMA):
        item = dict(parent_schema=schema, input_role='runtime', implementation_reference=ref('legacy_publisher'),
            reader_reference=nodes[0]['reader_reference'])
        # Each legacy fixture has a distinct reader path; production host lists
        # exact fixed implementation roles, so model that explicitly per node.
        for node in nodes:
            if node['document']['history']['schema'] == schema:
                entry = dict(item, reader_reference=node['reader_reference'])
                if schema == contract.TERMINAL_SCHEMA:
                    entry['terminal_reference'] = base['reference']
                legacy.append(entry)
    lookup = {(node['reference']['path'], node['reference']['sha256']): node for node in nodes}
    return nodes, lookup, legacy


class AncestryContractTests(unittest.TestCase):
    def inspect(self, nodes, lookup, legacy):
        return contract.inspect_ancestry_graph({role: nodes[-1][role] for role in contract.PARENT_ROLES},
            lookup, bound_pair=pair(), legacy_implementations=legacy)

    def test_alternating_global_budget_and_detached_oldest_first(self):
        # Use one host role per actual/gap schema, as real fixed peers do.
        nodes, lookup, legacy = graph(4)
        result = self.inspect(nodes, lookup, legacy)
        self.assertEqual([item['kind'] for item in result['work_items']], ['terminal', 'actual', 'gap', 'actual'])
        self.assertEqual(result['parent_node_count'], 4)
        self.assertFalse(result['file_bytes_read'])
        result['work_items'][0]['child_references']['reference']['path'] = '/changed'
        self.assertEqual(nodes[0]['reference']['path'], 'E:/graph/0/reference')

    def test_same_pair_two_successive_structural_actual_edges(self):
        nodes, lookup, legacy = graph(1)
        for day in ('14', '15'):
            node = envelope(day, contract.ACTUAL_SCHEMA,
                {role: nodes[-1][role] for role in contract.PARENT_ROLES}, modern=True)
            nodes.append(node)
            lookup[(node['reference']['path'], node['reference']['sha256'])] = node
        result = self.inspect(nodes, lookup, legacy)
        self.assertEqual([item['implementation_role'] for item in result['work_items']],
            ['HOST_FIXED_LEGACY_IMPLEMENTATION', 'HOST_BOUND_CURRENT_PAIR', 'HOST_BOUND_CURRENT_PAIR'])

    def test_host_binding_peer_and_algorithm_swaps_fail(self):
        nodes, lookup, legacy = graph(1)
        node = envelope('14', contract.ACTUAL_SCHEMA, {role: nodes[0][role] for role in contract.PARENT_ROLES}, modern=True)
        contract.classify_parent_edge(node, bound_pair=pair(), legacy_implementations=legacy)
        for field in ('implementation_pair_binding_reference', 'ancestry_contract_reference'):
            changed = deepcopy(node)
            for name in ('document', 'publication', 'readback'):
                changed[name][field] = ref('attacker_' + field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                contract.classify_parent_edge(changed, bound_pair=pair(), legacy_implementations=legacy)
        changed = deepcopy(node)
        for name in ('document', 'publication', 'readback'):
            changed[name]['input_references']['dependencies'] = {'history_core': ref('other_algorithm')}
        with self.assertRaises(ValueError):
            contract.classify_parent_edge(changed, bound_pair=pair(), legacy_implementations=legacy)

    def test_all_four_references_and_original_observation_association(self):
        nodes, lookup, legacy = graph(2)
        changed = deepcopy(lookup)
        key = (nodes[-1]['reference']['path'], nodes[-1]['reference']['sha256'])
        changed[key]['publication_reference'] = ref('different_publication')
        with self.assertRaises(ValueError):
            self.inspect(nodes, changed, legacy)
        changed = deepcopy(nodes[-1])
        changed['document']['history']['observation_references']['receipt_reference'] = ref('wrong_receipt')
        with self.assertRaises(ValueError):
            contract.classify_parent_edge(changed, bound_pair=pair(), legacy_implementations=legacy)

    def test_missing_envelope_and_unknown_terminal_fail(self):
        nodes, lookup, legacy = graph(3)
        del lookup[(nodes[0]['reference']['path'], nodes[0]['reference']['sha256'])]
        with self.assertRaises(ValueError):
            self.inspect(nodes, lookup, legacy)
        nodes, lookup, legacy = graph(1)
        legacy[0]['terminal_reference'] = ref('unapproved_base')
        with self.assertRaises(ValueError):
            self.inspect(nodes, lookup, legacy)

    def test_exact_128_global_nodes_then_129_rejected(self):
        # Avoid an artificial large host implementation table: all nodes share
        # each schema's exact immutable reader implementation reference.
        nodes, lookup, legacy = graph(129)
        legacy = []
        for schema in (contract.TERMINAL_SCHEMA, contract.ACTUAL_SCHEMA, contract.GAP_SCHEMA):
            item = dict(parent_schema=schema, input_role='runtime', implementation_reference=ref('legacy_publisher'),
                reader_reference=ref('shared_' + schema))
            if schema == contract.TERMINAL_SCHEMA:
                item['terminal_reference'] = nodes[0]['reference']
            legacy.append(item)
        for node in nodes:
            reader = ref('shared_' + node['document']['history']['schema'])
            node['reader_reference'] = reader
        for index, node in enumerate(nodes[1:], 1):
            prior = {role: nodes[index-1][role] for role in contract.PARENT_ROLES}
            node['document']['history']['parent_references'] = deepcopy(prior)
            for name in ('document', 'publication', 'readback'):
                node[name]['input_references']['parent'] = deepcopy(prior)
        self.assertEqual(self.inspect(nodes[:128], lookup, legacy)['parent_node_count'], 128)
        with self.assertRaises(ValueError):
            self.inspect(nodes, lookup, legacy)

    def test_actual_gap_cycle_fails_with_one_global_visited_set(self):
        nodes, lookup, legacy = graph(3)
        prior = {role: nodes[-1][role] for role in contract.PARENT_ROLES}
        nodes[1]['document']['history']['parent_references'] = deepcopy(prior)
        for name in ('document', 'publication', 'readback'):
            nodes[1][name]['input_references']['parent'] = deepcopy(prior)
        with self.assertRaises(ValueError):
            self.inspect(nodes, lookup, legacy)


if __name__ == '__main__':
    unittest.main()
