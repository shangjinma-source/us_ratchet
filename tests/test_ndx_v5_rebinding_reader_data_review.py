"""Independent bounded V5 readback attacks; synthetic inputs only."""
from copy import deepcopy
import itertools
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_v5_completed_task_rebinding_independent_readback_20260925 as owner
from scripts import ndx_new_cutoff_v5_completed_task_rebinding_independent_readback_20260925 as m

class Tests(unittest.TestCase):
    def test_rank_matches_tiny_explicit_prefix_order(self):
        groups=[dict(issuer_id=f'I{i}',security_ids=members) for i,members in enumerate([['z'],['a','b'],['x'],['c','d']])]
        for k in (1,2,3,4):
            choices=[]
            def visit(start,prefix):
                if len(prefix)==k:choices.append(prefix);return
                for group in groups[start:]:
                    pos=groups.index(group)
                    for sid in group['security_ids']:visit(pos+1,prefix+[sid])
            visit(0,[])
            self.assertEqual([m.independent_rank(groups,s) for s in choices],list(range(len(choices))))
    def test_rehashed_location_and_nested_evidence_still_rejected(self):
        docs,panel=owner.fixture()
        with patch.object(m.codec,'decode_frames',return_value=panel):rows=m.reconstruct_rows(docs)
        envelope=dict(schema='NEW_CUTOFF_V5_COMPLETED_TASK_REBINDING_V1',input_references={k:m.ref(k) for k in m.BOUND},rows=rows,externally_rebound_task_count=300,externally_rebound_combination_count=100,full_plan_task_denominator=18868155,remaining_uncompleted_task_count=18867855,new_wrapper_call_attempt_count=0,new_fit_count=0,old_full_tasks_and_completion_references_preserved=True,rank_calculation_performed=True,combination_enumeration_performed=False,complete_observed_provenance_and_missing=docs['plan']['complete_observed_provenance_and_missing'],preserved_sidecar_references=[docs['plan'][key] for key in owner.KEYS],source_hashes={},**dict.fromkeys(m.PRODUCER_FALSE,False))
        with patch.object(m,'reconstruct_rows',return_value=rows),patch.object(m,'producer_sources',return_value={}):
            m.verify_candidate(envelope,docs)
            for attack in ('rank','nested','references','permissions'):
                bad=deepcopy(envelope)
                if attack=='rank':
                    bad['rows'][0]['new_location_identity']['rank']+=1
                    bad['rows'][0]['new_location_id']=m.digest(bad['rows'][0]['new_location_identity'])
                elif attack=='nested':bad['rows'][-1]['original_index_row'].pop('prior_rebinding_row')
                elif attack=='references':bad['rows'][102]['old_completed_row']['raw_reference']['sha256']='0'*64
                else:bad['promotion_allowed']=True
                with self.subTest(attack=attack),self.assertRaises(ValueError):m.verify_candidate(bad,docs)
    def test_pending_boolean_and_unselected_cell_are_not_accepted(self):
        docs,panel=owner.fixture()
        for field in ('external_completed_tasks_deducted',):
            bad=deepcopy(docs);bad['plan'][field]=False
            with patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.reconstruct_rows(bad)
        panel['returns'].loc[panel['returns'].index[0],'ORLY']=float('nan')
        with patch.object(m.codec,'decode_frames',return_value=panel),self.assertRaises(ValueError):m.reconstruct_rows(docs)
    def test_hard_pins_and_loaded_source_conflicts(self):
        self.assertEqual(m.codec.sha(m.PRODUCER.read_bytes()),m.PRODUCER_SHA)
        self.assertEqual(m.codec.sha(m.CANDIDATE.read_bytes()),m.CANDIDATE_SHA)
        path=next(iter(m.LOADED))
        with self.assertRaises(ValueError):m.guard({path:'0'*64})

if __name__=='__main__':unittest.main()
