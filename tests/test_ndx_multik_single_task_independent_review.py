"""Saved metadata and temporary mock attempts only; no real fitter invocation."""
from copy import deepcopy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_multik_single_task_20260924 as owner
from scripts import ndx_new_cutoff_multik_single_task_20260924 as m


class IndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        owner.Tests.setUpClass();cls.docs=owner.Tests.docs;cls.sources=owner.Tests.numerical

    def test_k5_and_k19_actual_saved_grouping_and_pointers(self):
        with patch.object(m.fitter,'refit_dynamic_cutoff_weights') as fit:
            for slice_index in (1,15):
                task=self.docs['queue']['new_materializations'][slice_index]['combinations'][0]['tasks'][1]
                state=m.validate_inputs(self.docs,task['numerical_task_id'],self.sources)
                self.assertEqual(len(state['task']['numerical_identity']['selected']),slice_index+4)
                self.assertEqual(state['task_reference']['json_pointer'],f'/new_materializations/{slice_index}/combinations/0/tasks/1')
                self.assertEqual(state['returns'].shape,(126,20))
            fit.assert_not_called()

    def test_resigned_none_prior_replacement_and_missing_universe_rejected(self):
        for attack in ('prior','groups'):
            docs=deepcopy(self.docs);task=docs['queue']['new_materializations'][1]['combinations'][0]['tasks'][1]
            if attack=='prior':
                task['numerical_identity']['requested_previous_target_weights']={}
                task['numerical_task_id']=m.digest(task['numerical_identity'])
            else:docs['plan']['plan']['canonical_groups'].pop()
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.validate_inputs(docs,task['numerical_task_id'],self.sources)

    def test_k19_equal_float_original_risks_not_k4_assumption(self):
        task=self.docs['queue']['new_materializations'][15]['combinations'][0]['tasks'][0]
        identity=task['numerical_identity'];selected=identity['selected'];p=identity['parameters']
        weights=[1./19]*19;chains={}
        for sid in sorted(selected):
            chain=selected[sid]['risk_chain'];chains[chain]=chains.get(chain,0)+1./19
        checks=dict(MAX_SINGLE_WEIGHT=max(weights)<=p['max_single_weight']+1e-9,
            MIN_SINGLE_WEIGHT=min(weights)>=p['min_single_weight']-1e-9,
            SECURITY_TOP3_WEIGHT=sum(weights[:3])<=p['top_weight_cap']+1e-9,
            MINIMUM_EFFECTIVE_N=1/sum(w*w for w in weights)>=19*p['minimum_effective_n_ratio']-1e-9,
            RISK_CHAIN_TOP1_WEIGHT=max(chains.values())<=p['risk_chain_top1_cap']+1e-9)
        fitted=dict(schema='ndx_dynamic_cutoff_refit_research_v2',fit_data_sha256=identity['fit_data_sha256'],
            cutoff=identity['cutoff'],weight_spec=identity['weight_spec'],source_hashes=self.sources,
            previous_target_weights={},targets={sid:dict(ticker=row['ticker'],issuer_id=row['issuer_id'],target_weight=1./19) for sid,row in selected.items()},
            declared_constraint_checks=checks,declared_constraints_passed=all(checks.values()))
        with patch.object(m.fitter,'_sources',return_value=self.sources):
            self.assertEqual(m.postflight({'task':task},fitted),checks)

    def test_exclusive_attempt_race_blocks_before_any_fitter_call(self):
        task=self.docs['queue']['new_materializations'][1]['combinations'][0]['tasks'][1];tid=task['numerical_task_id']
        state=dict(task=task,returns=None,source_hashes={},runtime={})
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT_ROOT',Path(tmp)),patch.object(m,'preflight',return_value=state),patch.object(m,'guard'),patch.object(m,'runtime',return_value={}),patch.object(m.fitter,'refit_dynamic_cutoff_weights') as fit:
            (Path(tmp)/tid).mkdir()
            with self.assertRaises(FileExistsError):m.run(tid,execute=True)
            fit.assert_not_called()
            self.assertEqual(list((Path(tmp)/tid).iterdir()),[])


if __name__=='__main__':unittest.main()
