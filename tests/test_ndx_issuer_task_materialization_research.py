"""Only synthetic panels and tiny prefix slices; no original fitter is imported."""
from copy import deepcopy
from datetime import date,timedelta
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_issuer_task_materialization_research as m


def fixture(shard_size=2,prior=None):
    root=Path(__file__).resolve().parent
    groups=[('A',['zA1','zA2']),('B',['aB']),('C',['mC']),('D',['cD']),('E',['bE'])]
    parameters=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,
        min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
    plan=m.planning.prepare_issuer_shards(groups=groups,panel_reference=dict(path=str(root/'synthetic.json'),sha256='a'*64),
        panel_audit_reference=dict(path=str(root/'synthetic_audit.json'),sha256='b'*64),decision_cutoff='2026-09-21',parameters=parameters,
        fitter_source_hashes={str(root/'synthetic_fitter.py'):'c'*64},previous_target_weights=prior,shard_size=shard_size,max_shards=100)
    columns=['TA1','TA2','TB','TC','TD','TE'];names=['zA1','zA2','aB','mC','cD','bE'];issuers=['A','A','B','C','D','E']
    panel=dict(panel_reference=deepcopy(plan['context']['panel_reference']),panel_content_sha256='d'*64,
        dates=[(date(2026,9,21)-timedelta(days=i)).isoformat() for i in range(125,-1,-1)],columns=columns,
        returns=[[float(j+1)/1000 for j in range(6)] for _ in range(126)],
        universe=[dict(security_id=sid,ticker=ticker,issuer_id=issuer,risk_chain='chain_'+issuer) for sid,ticker,issuer in zip(names,columns,issuers)])
    shard=next(row for row in plan['shards'] if row['k']==4 and row['start']==0)
    return dict(plan=plan,plan_reference=dict(path=str(root/'synthetic_plan.json'),sha256='e'*64),shard_id=shard['shard_id'],panel=panel,start=0,stop=1,max_materialized_combinations=1)


class MaterializationTests(unittest.TestCase):
    def test_prefix_and_fitter_orders_and_original_matrix_digest(self):
        result=m.materialize_slice(**fixture());combo=result['combinations'][0]
        self.assertEqual(combo['prefix_security_ids'],['zA1','aB','mC','cD'])
        self.assertEqual(combo['fitter_sorted_security_ids'],['aB','cD','mC','zA1'])
        self.assertEqual(combo['fit_matrix']['tickers'],['TB','TD','TC','TA1'])
        expected=hashlib.sha256(json.dumps(combo['fit_matrix'],sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        self.assertEqual(combo['fit_data_sha256'],expected)
        self.assertEqual(len(combo['tasks']),3);self.assertEqual(len({row['numerical_task_id'] for row in combo['tasks']}),3)
        self.assertIsNone(combo['tasks'][0]['numerical_identity']['requested_previous_target_weights'])
        self.assertEqual(combo['tasks'][0]['expected_fitter_previous_target_weights'],{})

    def test_shard_boundary_changes_location_not_numerical_identity(self):
        first=m.materialize_slice(**fixture(2))['combinations'][0]['tasks']
        second=m.materialize_slice(**fixture(3))['combinations'][0]['tasks']
        for a,b in zip(first,second):
            self.assertEqual(a['numerical_task_id'],b['numerical_task_id']);self.assertNotEqual(a['location_id'],b['location_id'])

    def test_full_exiting_prior_and_strict_fitter_gate_before_slice(self):
        previous={'EXITED_SID':.75,'aB':.25};result=m.materialize_slice(**fixture(prior=previous))
        for task in result['combinations'][0]['tasks']:
            self.assertEqual(task['numerical_identity']['requested_previous_target_weights'],previous)
            self.assertEqual(task['expected_fitter_previous_target_weights'],previous)
        bad=fixture(prior={'EXITED_SID':.5,'aB':.50000000005})
        with patch.object(m.indexing.IssuerCombinationIndex,'slice',side_effect=AssertionError('enumerated')),self.assertRaisesRegex(ValueError,'1e-12'):
            m.materialize_slice(**bad)

    def test_all_panel_cells_and_full_groups_checked_before_slice(self):
        for attack in ('bool','future','missing','unselected_group','budget','planstate'):
            args=fixture()
            if attack=='bool':args['panel']['returns'][0][-1]=True
            elif attack=='future':args['panel']['dates'][-1]='2026-09-22'
            elif attack=='missing':args['panel']['returns'][1].pop()
            elif attack=='unselected_group':args['panel']['universe'][-1]['issuer_id']='OTHER'
            elif attack=='budget':args['stop']=2
            else:args['plan']['completed_canonical_task_count']=1
            with self.subTest(attack=attack),patch.object(m.indexing.IssuerCombinationIndex,'slice',side_effect=AssertionError('enumerated')),self.assertRaises(ValueError):
                m.materialize_slice(**args)

    def test_matrix_parameter_source_and_prior_change_numerical_id(self):
        baseline=m.materialize_slice(**fixture())['combinations'][0]['tasks'][0]['numerical_task_id']
        for attack in ('matrix','parameter','source','prior'):
            args=fixture()
            if attack=='matrix':args['panel']['returns'][0][2]=.015
            elif attack=='prior':args=fixture(prior={'EXIT':.5,'aB':.5})
            else:
                plan=args['plan'];context=plan['context'];parameters=deepcopy(context['parameters']);sources=deepcopy(plan['fitter_source_hashes'])
                if attack=='parameter':parameters['shrinkage_intensity']=.36
                else:sources[next(iter(sources))]='f'*64
                args['plan']=m.planning.prepare_issuer_shards(groups=[(row['issuer_id'],row['security_ids']) for row in plan['canonical_groups']],
                    panel_reference=context['panel_reference'],panel_audit_reference=context['panel_audit_reference'],decision_cutoff=context['decision_cutoff'],
                    parameters=parameters,fitter_source_hashes=sources,previous_target_weights=None,shard_size=2,max_shards=100)
                args['shard_id']=next(row['shard_id'] for row in args['plan']['shards'] if row['k']==4 and row['start']==0)
            with self.subTest(attack=attack):self.assertNotEqual(m.materialize_slice(**args)['combinations'][0]['tasks'][0]['numerical_task_id'],baseline)

    def test_only_requested_slice_positions_and_no_completion_claim(self):
        args=fixture();args.update(start=1,stop=2)
        original=m.indexing.IssuerCombinationIndex.unrank;calls=[]
        def watch(this,k,rank):calls.append(rank);return original(this,k,rank)
        with patch.object(m.indexing.IssuerCombinationIndex,'unrank',watch):result=m.materialize_slice(**args)
        self.assertEqual(calls,[1]);self.assertEqual(result['completed_task_count'],0)
        self.assertFalse(result['full_shard_completed']);self.assertFalse(result['fit_performed'])


if __name__=='__main__':unittest.main()
