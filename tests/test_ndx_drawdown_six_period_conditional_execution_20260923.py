"""Synthetic inputs only; never prepare actual evidence or execute an account."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_drawdown_six_period_conditional_execution_20260923 as m


def inputs():
    calendar=json.loads((m.BASE/'return_six_period_benchmarks_20260923_v1/benchmarks.json').read_bytes())['calendar']
    selected={f'security:{cik}:{cusip}':dict(ticker=t,issuer_id=f'issuer:{cik}',risk_chain=chain)
        for t,(cik,cusip,chain) in m.COORDINATES.items()}
    targets={sid:dict(ticker=row['ticker'],issuer_id=row['issuer_id'],target_weight=.25) for sid,row in selected.items()}
    schedule=[dict(decision_date=d,execution_date=e,targets=deepcopy(targets)) for d,e in m.CLOCK]
    chains={d:{sid:row['risk_chain'] for sid,row in selected.items()} for d,e in m.CLOCK}
    target=dict(schema='DRAWDOWN_SIX_PERIOD_STRATEGIC_TARGET_SCHEDULE_V1',schedule=schedule,calendar=calendar,
        risk_chains_by_decision=deepcopy(chains),promotion_allowed=False,member_point_in_time_verified=False,
        whole_lot_execution_performed=False,all_six_targets_passed=True)
    assembly=dict(schema='DRAWDOWN_FOUR_SECURITY_107_SESSION_CONDITIONAL_INPUT_V1',lane='DRAWDOWN',
        calendar=calendar,observed_decision_clock=[list(x) for x in m.CLOCK],security_count=4,distinct_issuer_count=4,
        saved_lane_choices=[dict(decision_date=d,execution_date=e,saved_candidate={'selected':deepcopy(selected)}) for d,e in m.CLOCK],
        selected_risk_chains_by_decision=deepcopy(chains),point_in_time_verified=False,promotion_allowed=False,
        execution_risk_chain_union_verified=False,target_schedule_validity_verified=False,
        identity_projection=dict(rows=[dict(security_id=sid,**row) for sid,row in selected.items()],
            conditional_window=dict(start='2023-03-31',end='2023-09-01'),enph_original_interval_certification_extended=False,
            enph_original_conditional_window=dict(start='2023-03-31',end='2023-05-01'),
            interval_stability_assumption='NEW_EXPLICIT_107_DAY_STABILITY_ASSUMPTION_USING_DATED_FACTS_NOT_INTERVAL_CERTIFICATION'),
        price_projection=dict(tickers=sorted(m.COORDINATES),price_cell_count=856,session_count=107,ticker_count=4,
            matrices={k:{d:{t:'100.125' for t in m.COORDINATES} for d in calendar} for k in ('open','close')}))
    return target,assembly


def state():
    return dict(prepared=dict(calendar=[],schedule=[],columns={},contract=dict(m.CONTRACT),normalization_evidence={},
        price_conversion_evidence={},engine_input_validation={},risk_chain_evidence={},arguments={},normalized=[]),
        sources={},runtime={},resolution={})


class RunnerTests(unittest.TestCase):
    def test_four_security_shared_chain_and_frozen_column_validators(self):
        target,assembly=inputs()
        with patch.object(m.engine,'simulate_dynamic_frozen_execution_research',side_effect=AssertionError('No engine')) as engine, \
                patch.object(m.engine.repair,'_strict_price_index',wraps=m.engine.repair._strict_price_index) as validator:
            prepared=m.assemble(target,assembly)
            engine.assert_not_called();self.assertEqual(validator.call_count,2)
        self.assertEqual(prepared['schedule'],target['schedule'])
        self.assertEqual(prepared['price_conversion_evidence']['cell_count'],856)
        self.assertEqual(len(prepared['columns']),4)
        for chains in prepared['arguments']['risk_chains_by_decision'].values():
            self.assertEqual(len(set(chains.values())),3)
            self.assertEqual(list(chains.values()).count('energy_technology'),2)
        self.assertTrue(all(isinstance(row[k],Decimal) for day in prepared['prices'].values() for row in day.values() for k in ('open','close')))
        bad=deepcopy(prepared['arguments'])
        for k in ('open','close'):bad[k+'s'].columns=[c.lower() for c in bad[k+'s'].columns]
        with self.assertRaises(ValueError):m.validate_engine_inputs(bad)

    def test_split_energy_chain_and_identity_upgrade_rejected(self):
        target,assembly=inputs();sid='security:0001463101:29355A107'
        for row in assembly['saved_lane_choices']:row['saved_candidate']['selected'][sid]['risk_chain']='independent_enph'
        with self.assertRaises(ValueError):m.assemble(target,assembly)
        target,assembly=inputs();assembly['identity_projection']['enph_original_interval_certification_extended']=True
        with self.assertRaises(ValueError):m.assemble(target,assembly)

    def test_bad_price_and_clock_rejected(self):
        for attack in ('price','clock','count'):
            target,assembly=inputs()
            if attack=='price':assembly['price_projection']['matrices']['open'][assembly['calendar'][0]]['ENPH']=True
            if attack=='clock':target['schedule'][-1]['execution_date']='2023-09-05'
            if attack=='count':assembly['price_projection']['price_cell_count']=1070
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(target,assembly)

    def test_placeholder_and_copied_namespace_fail_closed(self):
        with patch.dict(m.BOUND,{'schedule':('unused','PENDING_FINAL_HARD_SHA')}):
            with self.assertRaises(ValueError):m.reference('schedule')
        with patch.object(m,'prepare') as prepare:
            with self.assertRaises(ValueError):m.run(m.OUTPUT.with_name('copy'),True)
            with self.assertRaises(ValueError):m.run(m.OUTPUT,1)
            prepare.assert_not_called()

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
