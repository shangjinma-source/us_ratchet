"""Independent edge-association attacks; no IO or arithmetic claim for K."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from backtest import ndx_compact_ancestry_contract_research_v1 as contract
from test_ndx_compact_ancestry_contract_research_v1 import graph,pair,envelope,ref


def four(node):return {role:deepcopy(node[role])for role in contract.PARENT_ROLES}


class IndependentAncestryContractTests(unittest.TestCase):
    def inspect(self,nodes,lookup,legacy):
        return contract.inspect_ancestry_graph(four(nodes[-1]),lookup,bound_pair=pair(),legacy_implementations=legacy)

    def test_artifact_binding_and_peer_roles_never_select_host_pair(self):
        base,_,legacy=graph(1)
        original=envelope('independent_current',contract.ACTUAL_SCHEMA,four(base[0]),modern=True)
        contract.classify_parent_edge(original,bound_pair=pair(),legacy_implementations=legacy)
        for kind in ('binding','contract','publisher','reader','dependency_extra','dependency_missing'):
            node=deepcopy(original)
            for field in ('document','publication','readback'):
                body=node[field]
                if kind=='binding':body['implementation_pair_binding_reference']=ref('unknown_host_B')
                if kind=='contract':body['ancestry_contract_reference']=ref('unknown_K')
                if kind=='publisher':body['input_references']['runtime']=pair()['independent_reader_reference']
                if kind=='dependency_extra':body['input_references']['dependencies']['undeclared']=ref('other')
                if kind=='dependency_missing':body['input_references']['dependencies'].clear()
            if kind=='reader':node['reader_reference']=pair()['publisher_reference']
            with self.subTest(kind=kind),self.assertRaises(ValueError):contract.classify_parent_edge(node,bound_pair=pair(),legacy_implementations=legacy)

    def test_every_parent_anchor_is_checked_against_loaded_envelope(self):
        nodes,lookup,legacy=graph(4);self.inspect(nodes,lookup,legacy)
        for role in contract.PARENT_ROLES:
            changed=deepcopy(lookup);key=(nodes[-1]['reference']['path'],nodes[-1]['reference']['sha256'])
            changed[key][role]['sha256']='b'*64
            with self.subTest(role=role),self.assertRaises(ValueError):self.inspect(nodes,changed,legacy)

    def test_actual_gap_self_cycles_and_same_path_different_hash_rejected(self):
        for index in (1,2):
            nodes,lookup,legacy=graph(4);self.inspect(nodes,lookup,legacy)
            prior=four(nodes[index]);nodes[index]['document']['history']['parent_references']=prior
            for field in ('document','publication','readback'):nodes[index][field]['input_references']['parent']=deepcopy(prior)
            with self.subTest(kind=nodes[index]['document']['history']['schema']),self.assertRaises(ValueError):self.inspect(nodes,lookup,legacy)
        nodes,lookup,legacy=graph(3);self.inspect(nodes,lookup,legacy)
        top=nodes[-1];old=deepcopy(top['reference']);top['reference']=dict(path=nodes[0]['reference']['path'],sha256='b'*64)
        for field in ('publication','readback'):top[field]['history_reference']=deepcopy(top['reference'])
        del lookup[(old['path'],old['sha256'])];lookup[(top['reference']['path'],top['reference']['sha256'])]=top
        with self.assertRaises(ValueError):self.inspect(nodes,lookup,legacy)

    def test_canonical_role_alias_and_mixed_graph_alias_rejected(self):
        base,_,_=graph(1);roles=four(base[0]);path=roles['reference']['path']
        roles['publication_reference']=dict(path=path.swapcase(),sha256='b'*64)
        with self.assertRaises(ValueError):contract.references(roles,contract.PARENT_ROLES)
        nodes,lookup,legacy=graph(3);self.inspect(nodes,lookup,legacy)
        top=nodes[-1];old=deepcopy(top['reference']);basepath=nodes[0]['reference']['path']
        separator='\\'if'\\'in basepath else '/'
        parent,_,name=basepath.rpartition(separator)
        top['reference']=dict(path=parent+separator+'alias'+separator+'..'+separator+name,sha256='b'*64)
        for field in ('publication','readback'):top[field]['history_reference']=deepcopy(top['reference'])
        del lookup[(old['path'],old['sha256'])];lookup[(top['reference']['path'],top['reference']['sha256'])]=top
        with self.assertRaises(ValueError):self.inspect(nodes,lookup,legacy)

    def test_host_terminal_exact_and_duplicate_legacy_roles_fail(self):
        nodes,lookup,legacy=graph(1);result=self.inspect(nodes,lookup,legacy)
        self.assertEqual(result['work_items'][0]['kind'],'terminal')
        wrong=deepcopy(legacy);wrong[0]['terminal_reference']['sha256']='b'*64
        with self.assertRaises(ValueError):self.inspect(nodes,lookup,wrong)
        with self.assertRaises(ValueError):self.inspect(nodes,lookup,[*legacy,deepcopy(legacy[0])])
        with self.assertRaises(ValueError):self.inspect(nodes,lookup,[])

    def test_typed_associations_detachment_and_scope_false(self):
        nodes,lookup,legacy=graph(4);result=self.inspect(nodes,lookup,legacy)
        self.assertEqual([item['kind']for item in result['work_items']],['terminal','actual','gap','actual'])
        for key in contract.FLAGS:self.assertIs(result[key],False)
        self.assertIs(result['file_bytes_read'],False);self.assertIs(result['append_algorithm_called'],False)
        for left,right in ((False,0),(True,1),([],()),({'v':False},{'v':0})):
            with self.subTest(left=left,right=right),self.assertRaises(ValueError):contract._same(left,right,'typed association')
        result['root_references']['reference']['path']='C:/mutated'
        self.assertNotEqual(nodes[-1]['reference']['path'],'C:/mutated')

    def test_real_fixed_v3_terminal_read_only_compatibility(self):
        from scripts import ndx_prospective_observation_writer_v3_20261009 as oldwriter
        refs=deepcopy(oldwriter.PARENT_BOUND);node=deepcopy(refs)
        for field,role in [('document','reference'),('publication','publication_reference'),('readback','readback_reference')]:
            raw=Path(refs[role]['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),refs[role]['sha256']);node[field]=json.loads(raw)
        self.assertEqual(node['document']['history']['schema'],contract.TERMINAL_SCHEMA)
        legacy=[dict(parent_schema=contract.TERMINAL_SCHEMA,input_role='pure',implementation_reference=node['document']['input_references']['pure'],reader_reference=refs['reader_reference'],terminal_reference=refs['reference'])]
        result=contract.inspect_ancestry_graph(refs,{(refs['reference']['path'],refs['reference']['sha256']):node},bound_pair=pair(),legacy_implementations=legacy)
        self.assertEqual(result['parent_node_count'],1);self.assertEqual(result['work_items'][0]['implementation_role'],'HOST_FIXED_LEGACY_IMPLEMENTATION')


if __name__=='__main__':unittest.main()
