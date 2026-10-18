"""Tiny synthetic rank rebinding; no real96 assembly or historical weight readback."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from scripts import ndx_new_cutoff_v3_completed_task_rebinding_20260925 as m


def fixture():
    index=m.indexing.IssuerCombinationIndex([('A',['sA']),('B',['sB']),('C',['sC'])])
    universe=pd.DataFrame([dict(security_id='s'+i,ticker=i,issuer_id=i,risk_chain='r'+i) for i in 'ABC'])
    panel=dict(universe=universe,returns=pd.DataFrame([[.01,.02,.03]]*126,columns=list('ABC'),index=pd.bdate_range('2026-01-01',periods=126)))
    sources={'synthetic':'a'*64};specs=['equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor']
    ctx=dict(decision_cutoff='2026-09-21',parameters={'fit_days':126},previous_target_weights=None,weight_specs=specs,order_version=m.indexing.ORDER_VERSION,group_fingerprint=index.group_fingerprint)
    plan=dict(context=ctx,fitter_source_hashes=sources,plan_id='b'*64,shards=[dict(k=2,start=0,stop=3,shard_id='c'*64)])
    selected={sid:{k:r[k] for k in ('ticker','issuer_id','risk_chain')} for r in universe.to_dict('records') if (sid:=r['security_id']) in ('sA','sC')}
    payload=dict(dates=[d.date().isoformat() for d in panel['returns'].index],tickers=['A','C'],returns=panel['returns'][['A','C']].to_numpy().tolist())
    identity=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=ctx['decision_cutoff'],holding_count=2,selected=selected,weight_spec=specs[0],parameters=ctx['parameters'],requested_previous_target_weights=None,fit_data_sha256=m.digest(payload),fitter_source_fingerprint=m.digest(sources))
    task=dict(numerical_identity=identity,numerical_task_id=m.digest(identity),location_identity={'old':'location'},location_id=m.digest({'old':'location'}),expected_fitter_previous_target_weights={})
    row=dict(full_task=task,numerical_task_id=task['numerical_task_id'],status='FITTED_FIVE_RISKS_PASSED',fit_data_sha256=m.digest(payload),raw_reference={'saved':'unchanged'})
    return row,{'pointer':'synthetic'},panel,plan,index


class Tests(unittest.TestCase):
    def test_new_location_old_task_and_evidence_unchanged(self):
        args=fixture();before=deepcopy(args[0])
        with patch.object(m.indexing.IssuerCombinationIndex,'slice',side_effect=AssertionError('no enumerate')):
            row=m.rebind(*args)
        self.assertEqual(row['new_location_identity']['rank'],1)
        self.assertEqual(row['old_completed_row'],before);self.assertEqual(args[0],before)
        self.assertEqual(row['new_wrapper_call_attempt_count'],0)

    def test_numeric_contract_changes_refuse_reuse(self):
        for attack in ('matrix','risk','parameter','source','prior'):
            args=fixture()
            if attack=='matrix':args[2]['returns'].iloc[0,0]=.4
            elif attack=='risk':args[2]['universe'].loc[0,'risk_chain']='changed'
            elif attack=='parameter':args[3]['context']['parameters']={'fit_days':125}
            elif attack=='source':args[3]['fitter_source_hashes']={'new':'b'*64}
            else:args[3]['context']['previous_target_weights']={'EXIT':1.0}
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.rebind(*args)

    def test_not_completed_and_shard_overlap_rejected(self):
        args=fixture();args[0]['status']='VALIDATION_FAILURE_RECORDED'
        with self.assertRaises(ValueError):m.rebind(*args)
        args=fixture();args[3]['shards']*=2
        with self.assertRaises(ValueError):m.rebind(*args)

    def test_immutable_namespace_and_source_guard(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(m,'OUTPUT',Path(folder)/'rebinding.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()
        with patch.object(m.Path,'read_bytes',return_value=b'drift'):
            with self.assertRaises(ValueError):m.guard({})


if __name__=='__main__':unittest.main()
