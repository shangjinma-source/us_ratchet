from copy import deepcopy
import unittest
from unittest.mock import patch
from scripts import ndx_drawdown_lane_prefix_independent_readback_20260923 as m
import test_ndx_return_lane_prefix_independent_review as fixture


class PrefixTests(unittest.TestCase):
    def step(self,index=2):
        args=fixture.ReturnPrefixReview().step('constrained_fixed_shrinkage' if index==5 else 'constrained_fixed_shrinkage_turnover_anchor')
        args['index']=index
        previous_selected={sid:dict(ticker=sid,issuer_id='issuer-'+sid,risk_chain='chain-'+sid) for sid in args['previous']}
        universe={**previous_selected,**args['selected']}
        binding=m.lane_binding(index=index,previous=args['previous'],previous_selected=previous_selected,selected=args['selected'],
            universe=universe,context_reference={'path':'context','sha256':'a'*64},input_binding={},
            import_reference={'path':'original','sha256':'b'*64},import_audit_reference={'path':'audit','sha256':'c'*64})
        args['binding']=binding
        for document in ('started','raw','final'):
            value=args[document];value['schema']=value['schema'].replace('RETURN','DRAWDOWN')
            value['plan_reference']=m.PLAN;value['execution_date']=m.DATES[index]
        args['started'].update(job_id='job',runtime={},source_hashes={},cutoff=m.CUTOFFS[index],numerical_and_lane_binding=deepcopy(binding))
        args['raw'].update(started_reference={},numerical_and_lane_binding=deepcopy(binding))
        args['final']['raw_reference']={}
        if index==5:
            args['started']['new_fit_attempt']=False;args['raw']['new_fit_attempt_count']=0
            fit=args['raw']['fitted'];fit.update(previous_target_weights={},surviving_anchor_mass=0,
                anchor_by_security={sid:0 for sid in args['selected']},effective_anchor_strength=0)
        return args

    def test_middle_fit_full_exited_sid_anchor_and_risk_union(self):
        args=self.step();result=m.validate_step(**args)
        self.assertEqual(result['exited_previous_sids'],['EXIT_D'])
        self.assertIn('EXIT_D',result['lane_risk_chains_by_security'])
        changed=deepcopy(args);changed['raw']['fitted']['previous_target_weights']=dict(changed['previous'])
        del changed['raw']['fitted']['previous_target_weights']['EXIT_D']
        with self.assertRaises(ValueError):m.validate_step(**changed)

    def test_last_original_prior_is_empty_but_lane_prior_is_full(self):
        args=self.step(5)
        self.assertTrue(m.validate_step(**args)['imported_original_fit'])
        for mutate in (lambda a:a['raw']['fitted'].update(previous_target_weights=a['previous']),
                       lambda a:a['raw'].update(new_fit_attempt_count=1),
                       lambda a:a['raw']['numerical_and_lane_binding'].update(lane_previous_target_weights={})):
            changed=deepcopy(args);mutate(changed)
            with self.assertRaises(ValueError):m.validate_step(**changed)

    def test_raw_extra_permission_and_boolean_count_rejected(self):
        for key,value in [('promotion_allowed',True),('new_fit_attempt_count',True)]:
            args=self.step();args['raw'][key]=value
            with self.assertRaises(ValueError):m.validate_step(**args)

    def test_prefix_exact_one_through_six(self):
        refs=[{'path':str(m.FOLDER/day/'finalization.json'),'sha256':'a'*64} for day in m.DATES]
        for n in range(1,7):self.assertEqual(m.prefix_references(refs[:n]),refs[:n])
        for wrong in ([],refs+[refs[-1]],refs[1:],refs[:1]+refs[2:3]):
            with self.assertRaises(ValueError):m.prefix_references(wrong)

    def test_universe_duplicate_sid_and_missing_exit_rejected(self):
        mapping={'columns':{'items':['ticker','security_id','issuer_id','risk_chain']},
            'column_values':{'items':[{'items':['A','B']},{'items':['same','same']},{'items':['i','j']},{'items':['r','s']}]}}
        with self.assertRaises(ValueError):m.universe_rows({'prepared_inputs':{'universe':{'payload':{'mapping':mapping}}}})
        with self.assertRaises(ValueError):m.lane_binding(index=1,previous={'OLD':1},previous_selected={},selected={},universe={},
            context_reference={},input_binding={},import_reference=None,import_audit_reference=None)

    def test_output_inside_target_directory_rejected_before_audit(self):
        with patch.object(m,'audit_prefix') as audit:
            with self.assertRaises(ValueError):m.run(finalization_paths=[],finalization_sha256=[],output=m.FOLDER/m.DATES[0]/'review.json')
            audit.assert_not_called()


if __name__=='__main__':unittest.main()
