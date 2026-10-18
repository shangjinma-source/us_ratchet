import copy
from datetime import date,timedelta
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_return_lane_prefix_independent_readback_20260923 as reader


class PrefixReadbackTests(unittest.TestCase):
    def fixture(self,index=1,spec='constrained_fixed_shrinkage_turnover_anchor'):
        selected={f'SID{i}':dict(ticker=f'T{i}',issuer_id=f'I{i}',risk_chain=f'R{i}') for i in range(4)}
        parameters=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,
            max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
        previous=None if index==0 else dict(SID0=.25,SID1=.25,SID2=.25,EXITING=.25)
        previous_ref=None if index==0 else dict(path='previous-raw',sha256='a'*64)
        checks={key:True for key in ('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')}
        mass=.75 if previous else 0.;anchor={sid:((previous or {}).get(sid,0.)/mass if mass else 0.) for sid in selected}
        fitted=dict(targets={sid:dict(ticker=row['ticker'],issuer_id=row['issuer_id'],target_weight=.25) for sid,row in selected.items()},
            risk_chains_by_security={sid:row['risk_chain'] for sid,row in selected.items()},
            previous_target_weights=previous or {},checkpoint_weights_used=False,weight_spec=spec,
            declared_parameters={key:value for key,value in parameters.items() if key!='fit_days'},
            surviving_anchor_mass=mass,anchor_by_security=anchor,
            effective_anchor_strength=.25 if previous and spec=='constrained_fixed_shrinkage_turnover_anchor' else 0.,
            declared_constraint_checks=checks,declared_constraints_passed=True,point_in_time_verified=False,
            source_authenticity_verified=False,promotion_allowed=False,historical_task_evaluation_performed=False,order_generation_allowed=False)
        common=dict(execution_date=reader.DATES[index],plan_reference=reader.PLAN)
        started=dict(common,schema='RETURN_TARGET_SINGLE_ATTEMPT_V1',cutoff=reader.CUTOFFS[index],
            new_fit_attempt=index>0,order_generation_allowed=False,selected=selected,parameters=parameters,weight_spec=spec,
            previous_target_weights=previous,previous_target_reference=previous_ref)
        raw=dict(common,schema='RETURN_TARGET_RAW_RESULT_V1',status='FIT_RETURNED',fitted=fitted,
            new_fit_attempt_count=1 if index else 0,first_fit_imported_without_refit=index==0,
            previous_target_weights=previous,previous_target_reference=previous_ref)
        final=dict(common,schema='RETURN_TARGET_STEP_FINALIZATION_V1',status='TARGET_FIVE_RISKS_PASSED',detail=None,
            risk_checks=checks,fallback_performed=False,whole_lot_execution_performed=False,promotion_allowed=False)
        return dict(index=index,started=started,raw=raw,final=final,selected=selected,parameters=parameters,
            weight_spec=spec,previous=previous,previous_reference=previous_ref)

    def test_exit_sid_is_preserved_in_full_previous_map(self):
        args=self.fixture();result=reader.validate_step(**args)
        self.assertEqual(result['exited_previous_sids'],['EXITING'])
        self.assertEqual(result['previous_target_sid_count'],4)
        for location in ('started','raw','fitted'):
            changed=copy.deepcopy(args)
            container=changed['raw']['fitted'] if location=='fitted' else changed[location]
            container['previous_target_weights']={key:value for key,value in args['previous'].items() if key!='EXITING'}
            with self.assertRaisesRegex(ValueError,'previous|Previous|anchor|strategic'):
                reader.validate_step(**changed)

    def test_equal_and_nonanchored_strength_must_be_zero(self):
        for spec in ('equal_weight','constrained_fixed_shrinkage'):
            args=self.fixture(spec=spec)
            self.assertEqual(reader.validate_step(**args)['effective_anchor_strength'],0.)
            args['raw']['fitted']['effective_anchor_strength']=.25
            with self.assertRaisesRegex(ValueError,'strength'):
                reader.validate_step(**args)

    def test_later_fit_count_is_one_and_foreign_plan_rejected(self):
        for index in range(1,6):
            args=self.fixture(index=index);reader.validate_step(**args)
            args['raw']['new_fit_attempt_count']=index+1
            with self.assertRaisesRegex(ValueError,'semantics'):
                reader.validate_step(**args)
        args=self.fixture();args['raw']['plan_reference']={'path':'other','sha256':'b'*64}
        with self.assertRaisesRegex(ValueError,'plan'):
            reader.validate_step(**args)

    def test_skipped_repeated_or_empty_prefix_rejected(self):
        refs=[dict(path=str(reader.FOLDER/day/'finalization.json'),sha256='a'*64) for day in reader.DATES]
        for size in range(1,7):self.assertEqual(len(reader.prefix_references(refs[:size])),size)
        for bad in ([],refs[1:2],[refs[0],refs[0]],refs+[refs[-1]]):
            with self.assertRaises(ValueError):reader.prefix_references(bad)

    def test_matrix_hash_and_calendar_are_recomputed(self):
        args=self.fixture();end=date.fromisoformat(reader.CUTOFFS[1]);dates=[];current=end
        while len(dates)<126:
            if current.weekday()<5:dates.append(current.isoformat())
            current-=timedelta(days=1)
        dates.reverse();columns=[f'T{i}' for i in range(4)]
        mapping=dict(index=dict(items=[dict(timestamp=day+'T00:00:00') for day in dates]),
            columns=dict(items=columns),column_values=dict(items=[dict(items=[{'float_hex':float(i/1000).hex()} for _ in dates]) for i in range(4)]))
        context={'prepared_inputs':{key:{'payload':{'mapping':copy.deepcopy(mapping)}} for key in ('returns','nominal_prices','target_returns')}}
        fitted=dict(fit_data_sha256=reader.digest(dict(dates=dates,tickers=columns,returns=[[i/1000 for i in range(4)] for _ in dates])),
            fit_start=dates[0],fit_end=dates[-1],cutoff=dates[-1],fit_row_count=126)
        reader.matrix_check(context,args['selected'],args['parameters'],dates[-1],fitted)
        fitted['fit_data_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'matrix'):
            reader.matrix_check(context,args['selected'],args['parameters'],dates[-1],fitted)

    def test_sources_conflict_and_extra_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'source.py');mapping={path:'a'*64}
            with self.assertRaisesRegex(ValueError,'Conflicting'):
                reader.merge_sources(mapping,{path:'b'*64})
            directory=Path(folder)/'step';directory.mkdir()
            for name in ('started.json','raw.json','finalization.json'):(directory/name).write_text('{}')
            reader.check_directory(directory)
            (directory/'orphan.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'extra'):
                reader.check_directory(directory)

    def test_source_drift_after_publication_cannot_report_success(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.py';source.write_text('original')
            report=dict(source_hashes={str(source):hashlib.sha256(source.read_bytes()).hexdigest()},status='PASSED',completed_prefix_count=1)
            with patch.object(reader,'audit_prefix',return_value=report),patch.object(reader.os,'fsync',side_effect=lambda _:source.write_text('changed')):
                with self.assertRaisesRegex(ValueError,'Source drift'):
                    reader.run(finalization_paths=['fixture'],finalization_sha256=['a'*64],output=Path(folder)/'report.json')


if __name__=='__main__':unittest.main()
