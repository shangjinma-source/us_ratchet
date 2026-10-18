"""Independent structural attacks; no physical family continuation claim."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_compact_ancestry_contract_research_v2 as graph
from backtest import ndx_continuation_consumer_metadata_research_v1 as metadata
from test_ndx_compact_ancestry_contract_research_v2 import context, four, node
from test_ndx_compact_ancestry_contract_research_v1 import graph as legacy_graph
from test_ndx_compact_implementation_pair_binding_research_v1 import reference


class IndependentGraphV2Tests(unittest.TestCase):
    def fixture(self, gap=True, provenance=True):
        host=context();bases,_,legacy=legacy_graph(1)
        value=node('independent_child',bases[0],host,gap=gap,provenance=provenance)
        args=dict(host,legacy_implementations=legacy)
        if gap:args['registered_gap_dependency_references']=deepcopy(value['document']['input_references']['dependencies'])
        return value,args

    def test_all_header_fields_and_host_context_mandatory(self):
        value,args=self.fixture()
        for field in ('document','publication','readback'):
            for key in metadata.METADATA_KEYS:
                changed=deepcopy(value);del changed[field][key]
                with self.subTest(field=field,key=key),self.assertRaises(ValueError):
                    graph.classify_parent_edge(changed,**args)
        for key in ('consumer_registry_view','consumer_registry_core_reference','metadata_contract_reference','registered_gap_dependency_references'):
            changed_args=deepcopy(args);changed_args[key]=None
            with self.subTest(hostkey=key),self.assertRaises(ValueError):
                graph.classify_parent_edge(value,**changed_args)

    def test_coordinated_artifact_role_binding_and_reader_swaps(self):
        value,args=self.fixture()
        fields=('implementation_pair_binding_reference','consumer_role_registry_reference',
            'ancestry_contract_reference','shared_ancestry_verifier_reference','consumer_registry_core_reference','consumer_metadata_contract_reference')
        for key in fields:
            changed=deepcopy(value)
            for part in ('document','publication','readback'):changed[part][key]=reference('foreign_'+key)
            with self.subTest(key=key),self.assertRaises(ValueError):graph.classify_parent_edge(changed,**args)
        for role in ('gap_publisher','capture_independent_reader','observation_independent_reader'):
            changed=deepcopy(value)
            changed['reader_reference']=deepcopy(args['consumer_registry_view']['consumer_references'][role])
            changed['readback']['reader_sha256']=changed['reader_reference']['sha256']
            with self.subTest(reader=role),self.assertRaises(ValueError):graph.classify_parent_edge(changed,**args)
        changed=deepcopy(value)
        for part in ('document','publication','readback'):
            changed[part]['input_references']['runtime']=deepcopy(args['consumer_registry_view']['consumer_references']['gap_independent_reader'])
        with self.assertRaises(ValueError):graph.classify_parent_edge(changed,**args)

    def test_current_actual_has_provenance_but_never_consumer_role(self):
        value,args=self.fixture(gap=False)
        self.assertEqual(graph.classify_parent_edge(value,**args)['implementation_role'],'HOST_BOUND_CURRENT_PAIR')
        for role in metadata.ADAPTERS:
            changed=deepcopy(value)
            for part in ('document','publication','readback'):
                changed[part].update(metadata.expected_consumer_metadata(consumer_role=role,**context()))
            with self.subTest(role=role),self.assertRaises(ValueError):graph.classify_parent_edge(changed,**args)
        changed=deepcopy(value)
        for part in ('document','publication','readback'):
            for key in ('consumer_role_registry_reference','consumer_registry_core_reference','consumer_metadata_contract_reference'):
                del changed[part][key]
        with self.assertRaises(ValueError):graph.classify_parent_edge(changed,**args)
        changed=deepcopy(value);changed['document']['shared_ancestry_verifier_reference']=reference('stray_verifier')
        with self.assertRaises(ValueError):graph.classify_parent_edge(changed,**args)

    def test_legacy_rejects_partial_continuation_headers_and_duplicate_allowlist(self):
        host=context();nodes,_,legacy=legacy_graph(3);value=nodes[-1]
        for field in ('document','publication','readback'):
            for key in metadata.METADATA_KEYS:
                changed=deepcopy(value)
                changed[field][key]='PARTIAL' if key in ('consumer_role','continuation_adapter_schema')else reference('stray')
                with self.subTest(field=field,key=key),self.assertRaises(ValueError):
                    graph.classify_parent_edge(changed,legacy_implementations=legacy,**host)
        duplicated=legacy+[deepcopy(next(item for item in legacy if item['parent_schema']==graph.GAP_SCHEMA))]
        with self.assertRaises(ValueError):graph.classify_parent_edge(value,legacy_implementations=duplicated,**host)

    def test_legacy_public_input_cannot_hide_partial_continuation_metadata(self):
        host=context();nodes,_,legacy=legacy_graph(3);value=nodes[-1]
        for key in ('consumer_role_registry','consumer_registry_core','consumer_metadata_contract','shared_ancestry_verifier'):
            changed=deepcopy(value)
            for part in ('document','publication','readback'):
                changed[part]['input_references'][key]=reference('stray_input_'+key)
            with self.subTest(key=key),self.assertRaises(ValueError):
                graph.classify_parent_edge(changed,legacy_implementations=legacy,**host)

    def test_current_pair_without_host_c_rejects_input_only_consumer_markers(self):
        host=context();bases,_,_=legacy_graph(1)
        value=node('no_C_current_actual',bases[0],host,gap=False,provenance=False)
        args=dict(bound_pair=host['bound_pair'])
        self.assertEqual(graph.classify_parent_edge(value,**args)['kind'],'actual')
        for key in ('consumer_role_registry','consumer_registry_core','consumer_metadata_contract','shared_ancestry_verifier'):
            changed=deepcopy(value)
            for part in ('document','publication','readback'):
                changed[part]['input_references'][key]=reference('stray_current_input_'+key)
            with self.subTest(key=key),self.assertRaises(ValueError):graph.classify_parent_edge(changed,**args)

    def test_windows_role_alias_and_cross_edge_path_cycle(self):
        value,args=self.fixture()
        changed=deepcopy(value)
        changed['publication_reference']['path']=changed['reference']['path'].upper().replace('/','\\')
        changed['readback']['publication_reference']=deepcopy(changed['publication_reference'])
        with self.assertRaises(ValueError):graph.classify_parent_edge(changed,**args)
        changed=deepcopy(value)
        alias=four(changed);alias['reference']['path']=changed['reference']['path'].upper().replace('/','\\')
        alias['reference']['sha256']='b'*64
        changed['document']['history']['parent_references']=deepcopy(alias)
        for part in ('document','publication','readback'):changed[part]['input_references']['parent']=deepcopy(alias)
        lookup={(changed['reference']['path'],changed['reference']['sha256']):changed}
        with self.assertRaisesRegex(ValueError,'Conflicting repeated parent path'):
            graph.inspect_ancestry_graph(four(changed),lookup,**args)

    def test_global128_inclusive_no_io_detached_across_all_edge_roles(self):
        host=context();base,_,legacy=legacy_graph(1);nodes=[base[0]]
        for index in range(1,129):nodes.append(node('global_'+str(index),nodes[-1],host,gap=index%2==0,provenance=True))
        dependencies=nodes[2]['document']['input_references']['dependencies']
        lookup={(item['reference']['path'],item['reference']['sha256']):item for item in nodes}
        original=deepcopy(nodes)
        with patch('builtins.open',side_effect=AssertionError('Pure graph IO')),patch.object(Path,'read_bytes',side_effect=AssertionError('Pure graph bytes')):
            result=graph.inspect_ancestry_graph(four(nodes[127]),lookup,legacy_implementations=legacy,registered_gap_dependency_references=dependencies,**host)
            self.assertEqual(result['parent_node_count'],128)
            with self.assertRaisesRegex(ValueError,'Global actual/gap cycle or depth'):
                graph.inspect_ancestry_graph(four(nodes[128]),lookup,legacy_implementations=legacy,registered_gap_dependency_references=dependencies,**host)
        self.assertEqual(nodes,original)
        for key in graph.FLAGS:self.assertIs(result[key],False)
        result['work_items'][0]['child_references'].clear();self.assertEqual(nodes,original)


if __name__=='__main__':unittest.main()
