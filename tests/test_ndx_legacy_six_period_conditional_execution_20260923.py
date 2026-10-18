"""Synthetic inputs only; never prepare actual evidence or execute an account."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_legacy_six_period_conditional_execution_20260923 as m


def inputs():
    calendar=json.loads((m.BASE/'return_six_period_benchmarks_20260923_v1/benchmarks.json').read_bytes())['calendar']
    lane=json.loads((m.BASE/'cutoff_training_lanes_20260923_v2/prepare.json').read_bytes())
    all_labels={f'security:{cik}:{cusip}':dict(ticker=t,issuer_id=f'issuer:{cik}',risk_chain=chain)
        for t,(cik,cusip,chain) in m.COORDINATES.items()}
    choices=[];schedule=[];chains={}
    for decision in lane['decisions']:
        choice=deepcopy(decision['lanes']['LEGACY_TARGET_DISTANCE'][0]);d=decision['cutoff'];e=decision['execution_date']
        choices.append(dict(decision_date=d,execution_date=e,saved_candidate=choice))
        selected=choice['selected'];chains[d]={sid:r['risk_chain'] for sid,r in selected.items()}
        schedule.append(dict(decision_date=d,execution_date=e,targets={sid:dict(ticker=r['ticker'],issuer_id=r['issuer_id'],
            target_weight=1/len(selected)) for sid,r in selected.items()}))
    target=dict(schema='LEGACY_TARGET_DISTANCE_SIX_PERIOD_STRATEGIC_TARGET_SCHEDULE_V1',schedule=schedule,calendar=calendar,
        risk_chains_by_decision=deepcopy(chains),promotion_allowed=False,member_point_in_time_verified=False,
        whole_lot_execution_performed=False,all_six_targets_passed=True,target_anchor_uses_actual_holdings=False)
    flags=dict.fromkeys(('point_in_time_verified','promotion_allowed','execution_risk_chain_union_verified',
        'target_schedule_validity_verified','provider_binding_verified','continuous_identity_interval_verified'),False)
    identity=dict(schema='LEGACY_TWELVE_CONDITIONAL_IDENTITY_ASSEMBLY_V1',calendar=calendar,
        rows=[dict(security_id=sid,**row,security_class='Class C' if row['ticker']=='GOOG' else 'Class A',
            continuous_interval_verified=False,provider_binding_verified=False,point_in_time_verified=False) for sid,row in all_labels.items()],
        observed_decision_clock=[list(x) for x in m.CLOCK],security_count=12,distinct_issuer_count=11,
        saved_lane_choices=choices,selected_risk_chains_by_decision=deepcopy(chains),
        conditional_window=dict(start='2023-03-31',end='2023-09-01'),enph_original_interval_certification_extended=False,
        enph_original_conditional_window=dict(start='2023-03-31',end='2023-05-01'),
        interval_stability_assumption='NEW_EXPLICIT_107_DAY_STABILITY_ASSUMPTION_USING_DATED_FACTS_NOT_INTERVAL_CERTIFICATION',
        goog_googl_relationship='DIFFERENT_SECURITY_IDS_SAME_ISSUER_NOT_A_RENAME',
        team_old_issuer_or_class_conversion_verified=False,dated_fact_availability_backdated=False,**flags)
    price=dict(schema='LEGACY_TWELVE_107_OBSERVED_SESSION_CONDITIONAL_PRICE_ONLY_V1',calendar=calendar,
        tickers=sorted(m.COORDINATES),price_cell_count=2568,session_count=107,ticker_count=12,
        matrices={k:{d:{t:'100.125' for t in m.COORDINATES} for d in calendar} for k in ('open','close')},
        dividend_cash_flows_modelled=False,corporate_action_completeness_verified=False,
        nominal_price_status='CONDITIONAL_RECONSTRUCTION_NOT_AUTHENTICATED',inherited_split_factors_reapplied=False,
        adjusted_close_used=False,**flags)
    return target,price,identity,lane


def state():
    return dict(prepared=dict(calendar=[],schedule=[],columns={},contract=dict(m.CONTRACT),normalization_evidence={},
        price_conversion_evidence={},engine_input_validation={},risk_chain_evidence={},arguments={},normalized=[],action_free_assumption={}),
        sources={},runtime={},resolution={})


class RunnerTests(unittest.TestCase):
    def test_twelve_marks_and_actual_uppercase_validators_no_engine(self):
        args=inputs()
        with patch.object(m.engine,'simulate_dynamic_frozen_execution_research',side_effect=AssertionError('No engine')) as engine, \
                patch.object(m.engine.repair,'_strict_price_index',wraps=m.engine.repair._strict_price_index) as validator:
            prepared=m.assemble(*args)
            engine.assert_not_called();self.assertEqual(validator.call_count,2)
        self.assertEqual([len(r['targets']) for r in prepared['schedule']],[4,4,4,4,6,4])
        self.assertEqual(prepared['price_conversion_evidence']['cell_count'],2568)
        self.assertEqual(len(prepared['columns']),12)
        self.assertEqual(len({r['issuer_id'] for r in prepared['labels'].values()}),11)
        self.assertFalse(prepared['action_free_assumption']['dividends_added_to_cash'])
        self.assertEqual(prepared['arguments']['corporate_actions'],[])
        self.assertTrue(all(isinstance(row[k],Decimal) for day in prepared['prices'].values() for row in day.values() for k in ('open','close')))

    def test_bad_price_clock_class_and_authority_rejected(self):
        for attack in ('price','clock','class','cashflow','count','future'):
            target,price,identity,lane=inputs()
            if attack=='price':price['matrices']['open'][price['calendar'][0]]['TEAM']=True
            if attack=='clock':target['schedule'][-1]['execution_date']='2023-09-05'
            if attack=='class':next(r for r in identity['rows'] if r['ticker']=='GOOGL')['security_class']='Class C'
            if attack=='cashflow':price['dividend_cash_flows_modelled']=True
            if attack=='count':price['price_cell_count']=856
            if attack=='future':target['risk_chains_by_decision']['2023-03-31']['security:0001650372:049468101']='cloud_application_software'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(target,price,identity,lane)

    def test_no_plan_and_two_rejections_do_not_refresh_old_chain(self):
        target,price,identity,lane=inputs();chains,evidence=m.causal_risk_chain_evidence(target,identity)
        old='security:0001652044:02079K305';new='security:0001652044:02079K107'
        self.assertEqual(evidence['2023-07-31']['observation_dates'][old],'2023-05-31')
        self.assertEqual(evidence['2023-07-31']['observation_dates'][new],'2023-07-31')
        self.assertNotIn(old,chains['2023-07-31'])
        prepared=dict(schedule=target['schedule'],risk_chain_evidence=evidence)
        daily=[];decisions=[]
        for index,row in enumerate(target['schedule']):
            day=row['decision_date'];held={old:2,new:3} if index>=4 else {old:2} if index else {};union=set(held)|set(row['targets'])
            observed=evidence[day]
            decisions.append(dict(decision_date=day,shares_before=held,status='NO_PLAN' if index==4 else 'PLANNED',
                risk_chains={sid:observed['chains'][sid] for sid in union},
                risk_chain_observation_dates={sid:observed['observation_dates'][sid] for sid in union}))
            daily.append(dict(session=day,shares=held,risk_chains={sid:observed['chains'][sid] for sid in held},
                risk_chain_observation_dates={sid:observed['observation_dates'][sid] for sid in held}))
        execution=dict(decisions=decisions,daily=daily,executions=[{'status':'REJECTED'},{'status':'REJECTED'}])
        self.assertTrue(m.verify_ledger_risk_history(execution,prepared)['actual_holdings_chain_dates_checked'])
        execution['daily'][4]['risk_chain_observation_dates'][old]='2023-07-31'
        with self.assertRaises(ValueError):m.verify_ledger_risk_history(execution,prepared)

    def test_placeholder_and_copied_namespace_fail_closed(self):
        with patch.dict(m.BOUND,{'schedule':('unused','PENDING_FINAL_HARD_SHA')}):
            with self.assertRaises(ValueError):m.reference('schedule')
        with patch.object(m,'prepare') as prepare:
            with self.assertRaises(ValueError):m.run(m.OUTPUT.with_name('copy'),True)
            with self.assertRaises(ValueError):m.run(m.OUTPUT,1)
            prepare.assert_not_called()

    def test_current_runner_source_cannot_be_replaced_by_archive(self):
        with patch.object(m.archive,'strict',side_effect=ValueError('loaded source drift')) as strict, \
                patch.object(m.archive,'verify_expected_sources') as fallback,patch.object(m,'runtime') as runtime:
            with self.assertRaisesRegex(ValueError,'loaded source drift'):m.check(state())
            strict.assert_called_once_with(m.LOADED)
            fallback.assert_not_called();runtime.assert_not_called()

    def test_raw_saved_before_failure_and_explicit_recovery_no_new_engine(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'attempt'
            with patch.object(m,'OUTPUT',output),patch.object(m,'prepare',return_value=state()),patch.object(m,'check'), \
                    patch.object(m,'reference',side_effect=lambda role:dict(path=role,sha256='a'*64)), \
                    patch.object(m.engine,'simulate_dynamic_frozen_execution_research',return_value={}) as engine, \
                    patch.object(m,'restore_and_audit',side_effect=ValueError('audit')):
                with self.assertRaisesRegex(ValueError,'audit'):m.run(output,True)
                failure=json.loads((output/'failure.json').read_bytes())
                self.assertTrue((output/'raw_execution.json').exists())
                with self.assertRaises(ValueError):m.run(output,True)
                with self.assertRaises(ValueError):m.recover(output,None,None)
                with patch.object(m,'restore_and_audit',return_value=({},{})):
                    m.recover(output,failure['started_reference']['sha256'],failure['raw_reference']['sha256'])
                self.assertEqual(engine.call_count,1)


if __name__=='__main__':unittest.main()
