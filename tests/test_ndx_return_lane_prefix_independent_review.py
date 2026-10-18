"""Independent counterexamples; no fit, owner validator or account engine."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_return_lane_prefix_independent_readback_20260923 as reader


class ReturnPrefixReview(unittest.TestCase):
    def step(self, weight_spec='constrained_fixed_shrinkage_turnover_anchor'):
        previous={sid:.25 for sid in ('A','B','C','EXIT_D')}
        selected={sid:{'ticker':sid,'issuer_id':'issuer-'+sid,'risk_chain':'chain-'+sid} for sid in ('A','B','C','NEW_E')}
        parameters=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,
                        max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,
                        minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
        reference={'path':'previous','sha256':'a'*64}
        checks={key:True for key in ('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')}
        fitted=dict(weight_spec=weight_spec,declared_parameters={key:value for key,value in parameters.items() if key!='fit_days'},
            targets={sid:{'ticker':sid,'issuer_id':row['issuer_id'],'target_weight':.25} for sid,row in selected.items()},
            previous_target_weights=previous,checkpoint_weights_used=False,surviving_anchor_mass=.75,
            anchor_by_security={sid:previous.get(sid,0)/.75 for sid in selected},
            effective_anchor_strength=.25 if weight_spec=='constrained_fixed_shrinkage_turnover_anchor' else 0,
            risk_chains_by_security={sid:row['risk_chain'] for sid,row in selected.items()},
            declared_constraint_checks=checks,declared_constraints_passed=True,
            point_in_time_verified=False,source_authenticity_verified=False,promotion_allowed=False,
            historical_task_evaluation_performed=False,order_generation_allowed=False)
        common=dict(plan_reference=reader.PLAN,execution_date=reader.DATES[2])
        started=dict(common,schema='RETURN_TARGET_SINGLE_ATTEMPT_V1',cutoff=reader.CUTOFFS[2],
            selected=selected,parameters=parameters,weight_spec=weight_spec,previous_target_reference=reference,
            previous_target_weights=previous,new_fit_attempt=True,order_generation_allowed=False)
        raw=dict(common,schema='RETURN_TARGET_RAW_RESULT_V1',status='FIT_RETURNED',fitted=fitted,
            new_fit_attempt_count=1,first_fit_imported_without_refit=False,
            previous_target_reference=reference,previous_target_weights=previous)
        final=dict(common,schema='RETURN_TARGET_STEP_FINALIZATION_V1',status='TARGET_FIVE_RISKS_PASSED',
            detail=None,risk_checks=checks,fallback_performed=False,whole_lot_execution_performed=False,promotion_allowed=False)
        return dict(index=2,started=started,raw=raw,final=final,selected=selected,parameters=parameters,
                    weight_spec=weight_spec,previous=previous,previous_reference=reference)

    def test_exit_sid_retained_in_full_prior_and_normalized_survivors(self):
        arguments=self.step()
        result=reader.validate_step(**arguments)
        self.assertEqual(result['exited_previous_sids'],['EXIT_D'])
        self.assertEqual(result['new_selected_sids'],['NEW_E'])
        self.assertEqual(result['previous_target_sid_count'],4)
        for target in ('started','raw','fitted'):
            changed=deepcopy(arguments)
            container=changed['raw']['fitted'] if target=='fitted' else changed[target]
            container['previous_target_weights']={key:value for key,value in arguments['previous'].items() if key!='EXIT_D'}
            with self.assertRaises(ValueError):
                reader.validate_step(**changed)

    def test_equal_and_unanchored_shrinkage_require_zero_strength(self):
        for spec in ('equal_weight','constrained_fixed_shrinkage'):
            arguments=self.step(spec)
            self.assertEqual(reader.validate_step(**arguments)['effective_anchor_strength'],0)
            arguments['raw']['fitted']['effective_anchor_strength']=.25
            with self.assertRaises(ValueError):
                reader.validate_step(**arguments)

    def matrix(self):
        cutoff='2023-05-31'
        days=[(date.fromisoformat(cutoff)-timedelta(days=125-index)).isoformat() for index in range(126)]
        mapping={'index':{'items':[{'timestamp':day+'T00:00:00'} for day in days]},
                 'columns':{'items':['AAA']},'column_values':{'items':[{'items':[{'float_hex':.01.hex()} for _ in days]}]}}
        context={'prepared_inputs':{key:{'payload':{'mapping':deepcopy(mapping)}} for key in ('returns','nominal_prices','target_returns')}}
        fitted=dict(fit_start=days[0],fit_end=cutoff,cutoff=cutoff,fit_row_count=126,
                    fit_data_sha256=reader.digest({'dates':days,'tickers':['AAA'],'returns':[[.01] for _ in days]}))
        return context,{'sid':{'ticker':'AAA'}},{'fit_days':126},cutoff,fitted

    def test_typed_matrix_exact_timestamp_and_finite_values(self):
        arguments=self.matrix()
        reader.matrix_check(*arguments)
        changed=deepcopy(arguments)
        changed[0]['prepared_inputs']['returns']['payload']['mapping']['index']['items'][0]['timestamp']=arguments[4]['fit_start']+'garbageT00:00:00'
        with self.assertRaises(ValueError):
            reader.matrix_check(*changed)
        changed=deepcopy(arguments)
        changed[0]['prepared_inputs']['returns']['payload']['mapping']['column_values']['items'][0]['items'][0]['float_hex']='nan'
        with self.assertRaises(ValueError):
            reader.matrix_check(*changed)

    def test_complete_one_through_six_prefix_only(self):
        references=[{'path':str(reader.FOLDER/day/'finalization.json'),'sha256':'a'*64} for day in reader.DATES]
        for count in range(1,7):
            self.assertEqual(len(reader.prefix_references(references[:count])),count)
        for invalid in ([],references+[references[-1]],[references[1]],references[:1]+references[2:3]):
            with self.assertRaises(ValueError):
                reader.prefix_references(invalid)

    def test_source_merge_cannot_overwrite_conflict(self):
        path=str(Path('fixture.py').resolve())
        sources={path:'a'*64}
        with self.assertRaises(ValueError):
            reader.merge_sources(sources,{path:'b'*64})
        self.assertEqual(sources[path],'a'*64)

    def test_numerical_closure_requires_all_and_only_hard_sources(self):
        expected={'fitter.py':'a'*64,'adapter.py':'b'*64}
        reader.check_numerical_sources({'source_hashes':dict(expected)},expected)
        for observed in ({},{'fitter.py':'a'*64},dict(expected,extra='c'*64),
                         dict(expected,**{'adapter.py':'c'*64})):
            with self.assertRaises(ValueError):
                reader.check_numerical_sources({'source_hashes':observed},expected)
        with self.assertRaises(ValueError):
            reader.check_numerical_sources({'source_hashes':{}},{})

    def test_source_drift_before_or_after_publish_is_rejected(self):
        for after in (False,True):
            with tempfile.TemporaryDirectory() as folder:
                source=Path(folder)/'source.py';source.write_bytes(b'original')
                output=Path(folder)/'audit.json'
                report={'source_hashes':{str(source):hashlib.sha256(b'original').hexdigest()},
                        'status':'PASSED','completed_prefix_count':1}
                def fake_audit(references):
                    if not after:source.write_bytes(b'changed')
                    return report
                with patch.object(reader,'audit_prefix',side_effect=fake_audit), \
                        patch.object(reader.os,'fsync',side_effect=lambda _:source.write_bytes(b'changed')):
                    with self.assertRaisesRegex(ValueError,'drift'):
                        reader.run(finalization_paths=['fixture'],finalization_sha256=['a'*64],output=output)


if __name__=='__main__':
    unittest.main()
