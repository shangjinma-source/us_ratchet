"""Synthetic groups and interval arithmetic; no production plan or combinations."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_issuer_shard_prepare_research as m


def arguments():
    root=Path(__file__).resolve().parent
    return dict(groups=[('E',['e']),('A',['a2','a1']),('B',['b']),('C',['c']),('D',['d'])],
        panel_reference=dict(path=str(root/'synthetic_panel.json'),sha256='a'*64),
        panel_audit_reference=dict(path=str(root/'synthetic_audit.json'),sha256='b'*64),
        decision_cutoff='2026-09-21',parameters=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,
            min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55),
        fitter_source_hashes={str(root/'synthetic_fitter.py'):'c'*64},previous_target_weights=None,shard_size=3,max_shards=100)


class ShardTests(unittest.TestCase):
    def test_counts_only_and_exact_interval_coverage_once(self):
        with patch.object(m.indexing.IssuerCombinationIndex,'slice',side_effect=AssertionError('enumerated')),\
             patch.object(m.indexing.IssuerCombinationIndex,'unrank',side_effect=AssertionError('enumerated')):
            value=m.prepare_issuer_shards(**arguments())
        self.assertEqual(value['all_k_combination_count'],47)
        self.assertEqual([row['k'] for row in value['cardinalities']],[1,2,3,4,5])
        excluded=0;planned=0
        for card in value['cardinalities']:
            shards=[row for row in value['shards'] if row['k']==card['k']]
            if card['necessary_bound_certificates']:
                excluded+=card['combination_count'];self.assertEqual(shards,[])
            else:
                position=0
                for shard in shards:self.assertEqual(shard['start'],position);position=shard['stop']
                self.assertEqual(position,card['combination_count']);planned+=position
        self.assertEqual(value['necessary_bound_excluded_combination_count'],excluded)
        self.assertEqual(planned+excluded,47);self.assertEqual(value['planned_canonical_task_count'],planned*3)
        self.assertEqual(value['completed_canonical_task_count'],0)
        self.assertEqual(value['remaining_canonical_task_count'],planned*3)
        self.assertEqual(len(value['context']['weight_specs']),3)
        self.assertFalse(value['anchor_alias_equivalence_verified'])

    def test_preserves_frozen_tolerance_certificates_not_exact_no_padding(self):
        args=arguments();value=m.prepare_issuer_shards(**args)
        risk={key:Fraction(str(args['parameters'][key])) for key in m.bounds._RISK_KEYS}
        for row in value['cardinalities']:self.assertEqual(row['necessary_bound_certificates'],m.bounds._necessary_bounds(row['k'],risk))
        self.assertEqual(value['conservative_bound_contract']['risk_tolerance'],'1/1000000000')
        self.assertEqual(value['conservative_bound_contract']['rounding_margin_per_term'],'1/1000000000000')
        self.assertGreater(len(value['cardinalities'][0]['necessary_bound_certificates']),1)

    def test_identity_changes_with_panel_audit_parameters_sources_and_full_prior(self):
        baseline=m.prepare_issuer_shards(**arguments())
        for change in ('panel','audit','parameter','sources','prior','cutoff'):
            args=arguments()
            if change=='panel':args['panel_reference']['sha256']='d'*64
            elif change=='audit':args['panel_audit_reference']['sha256']='e'*64
            elif change=='parameter':args['parameters']['shrinkage_intensity']=.36
            elif change=='sources':args['fitter_source_hashes'][next(iter(args['fitter_source_hashes']))]='f'*64
            elif change=='prior':args['previous_target_weights']={'EXITED_NOT_IN_CURRENT':.75,'a1':.25}
            else:args['decision_cutoff']='2026-09-22'
            value=m.prepare_issuer_shards(**args)
            with self.subTest(change=change):
                self.assertNotEqual(value['plan_id'],baseline['plan_id'])
                self.assertNotEqual(value['shards'][0]['shard_id'],baseline['shards'][0]['shard_id'])
            if change=='prior':self.assertEqual(value['shards'][0]['previous_target_weights'],args['previous_target_weights'])

    def test_canonical_group_input_order_and_descriptor_identity(self):
        args=arguments();first=m.prepare_issuer_shards(**args)
        args['groups'].reverse();second=m.prepare_issuer_shards(**args)
        self.assertEqual(first,second)
        for shard in first['shards']:
            identity=dict(first['context'],k=shard['k'],start=shard['start'],stop=shard['stop'])
            self.assertEqual(shard['shard_id'],m.digest(identity))
            self.assertEqual(shard['status'],'PLANNED_NOT_ENUMERATED')

    def test_bool_invalid_refs_sources_and_prior_rejected(self):
        for change in ('shardsize','budget','parameter','fitdays','ref','sources','priorbool','priormass','cutoff'):
            args=arguments()
            if change=='shardsize':args['shard_size']=True
            elif change=='budget':args['max_shards']=True
            elif change=='parameter':args['parameters']['top_weight_cap']=True
            elif change=='fitdays':args['parameters']['fit_days']=126.0
            elif change=='ref':args['panel_reference']['sha256']='A'*64
            elif change=='sources':args['fitter_source_hashes']={}
            elif change=='priorbool':args['previous_target_weights']={'exit':True}
            elif change=='priormass':args['previous_target_weights']={'exit':.5}
            else:args['decision_cutoff']=True
            with self.subTest(change=change),self.assertRaises(ValueError):m.prepare_issuer_shards(**args)

    def test_descriptor_budget_fails_before_any_shard_generation(self):
        args=arguments();args['max_shards']=1;args['shard_size']=1
        with self.assertRaisesRegex(ValueError,'Descriptor budget exceeded'):m.prepare_issuer_shards(**args)


if __name__=='__main__':unittest.main()
