from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_bad_tail_six_period_conditional_execution_20260923 as m


def risk_fixture():
    selected=[{'OLD':dict(ticker='OLD',issuer_id='i-old',risk_chain='old-chain')}]+[
        {'NEW':dict(ticker='NEW',issuer_id='i-new',risk_chain='new-chain')} for _ in range(5)]
    rows=[dict(decision_date=d,execution_date=e,targets={sid:{k:v[k] for k in ('ticker','issuer_id')} for sid,v in selected[i].items()}) for i,(d,e) in enumerate(m.CLOCK)]
    maps={d:{sid:v['risk_chain'] for sid,v in selected[i].items()} for i,(d,e) in enumerate(m.CLOCK)}
    return dict(schedule=rows,risk_chains_by_decision=deepcopy(maps)),dict(saved_lane_choices=[
        dict(decision_date=d,execution_date=e,saved_candidate={'selected':selected[i]}) for i,(d,e) in enumerate(m.CLOCK)],
        selected_risk_chains_by_decision=maps)


def state():
    prepared=dict(calendar=['fixture'],schedule=[{'targets':{'a':1}}],columns={},contract=dict(m.CONTRACT),normalization_evidence={},
        price_conversion_evidence={},engine_input_validation={},risk_chain_evidence={},arguments={},normalized=[])
    return dict(prepared=prepared,sources={},runtime={'test':1},resolution={})


class IndependentReview(unittest.TestCase):
    def test_saved_inputs_real_frozen_validators_and_decimal_boundary(self):
        target=m.read(m.reference('schedule'));projection=m.read(m.reference('projection'))
        with patch.object(m.engine.repair,'_strict_price_index',wraps=m.engine.repair._strict_price_index) as validator, \
                patch.object(m.engine,'simulate_dynamic_frozen_execution_research') as engine:
            prepared=m.assemble(target,projection)
            self.assertEqual(validator.call_count,2);engine.assert_not_called()
        self.assertEqual(len(prepared['calendar']),107)
        self.assertEqual(prepared['price_conversion_evidence']['cell_count'],1070)
        self.assertTrue(all(column==column.upper() for column in prepared['columns'].values()))
        self.assertEqual(prepared['contract'],m.CONTRACT)
        self.assertEqual(prepared['schedule'],target['schedule'])
        self.assertEqual(prepared['arguments']['corporate_actions'],[])
        for marks in prepared['prices'].values():
            for value in marks.values():
                for field in ('open','close'):self.assertEqual(m.independent.number(value[field]),value[field])
        corrupt=deepcopy(projection)
        day=corrupt['calendar'][0];ticker=corrupt['price_projection']['tickers'][0]
        corrupt['price_projection']['matrices']['open'][day][ticker]=True
        with self.assertRaises(ValueError):m.assemble(target,corrupt)

    def test_multiple_rejections_keep_original_observation_date(self):
        target,projection=risk_fixture();chains,evidence=m.causal_risk_chain_evidence(target,projection)
        for day,_ in m.CLOCK[1:]:
            self.assertEqual(evidence[day]['chains']['OLD'],'old-chain')
            self.assertNotIn('OLD',chains[day])
            self.assertEqual(evidence[day]['observation_dates']['OLD'],m.CLOCK[0][0])
        decisions=[];daily=[]
        for i,(day,_) in enumerate(m.CLOCK):
            union={'OLD'}|set(target['schedule'][i]['targets'])
            decisions.append(dict(decision_date=day,shares_before={'OLD':5},risk_chains={s:evidence[day]['chains'][s] for s in union},
                risk_chain_observation_dates={s:evidence[day]['observation_dates'][s] for s in union}))
            daily.append(dict(session=day,shares={'OLD':5},risk_chains={'OLD':'old-chain'},
                risk_chain_observation_dates={'OLD':m.CLOCK[0][0]}))
        execution=dict(decisions=decisions,daily=daily);prepared=dict(schedule=target['schedule'],risk_chain_evidence=evidence)
        m.verify_ledger_risk_history(execution,prepared)
        execution['daily'][2]['risk_chain_observation_dates']['OLD']=m.CLOCK[4][0]
        with self.assertRaises(ValueError):m.verify_ledger_risk_history(execution,prepared)

    def test_future_security_cannot_be_backfilled(self):
        target,projection=risk_fixture();target['risk_chains_by_decision'][m.CLOCK[0][0]]['NEW']='new-chain'
        with self.assertRaises(ValueError):m.causal_risk_chain_evidence(target,projection)

    def test_raw_survives_guard_failure_and_namespace_cannot_rerun(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'attempt'
            with patch.object(m,'OUTPUT',output),patch.object(m,'prepare',return_value=state()), \
                    patch.object(m,'check',side_effect=[None,None,ValueError('drift')]), \
                    patch.object(m,'reference',side_effect=lambda role:{'path':role,'sha256':'a'*64}), \
                    patch.object(m.engine,'simulate_dynamic_frozen_execution_research',return_value={}) as engine:
                with self.assertRaisesRegex(ValueError,'drift'):m.run(output,True)
                self.assertTrue((output/'raw_execution.json').exists())
                with self.assertRaises(ValueError):m.run(output,True)
                with self.assertRaises(ValueError):m.run(Path(folder)/'copy',True)
                self.assertEqual(engine.call_count,1)

    def test_failed_audit_external_hash_recovery_calls_engine_once_total(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'attempt'
            with patch.object(m,'OUTPUT',output),patch.object(m,'prepare',return_value=state()),patch.object(m,'check'), \
                    patch.object(m,'reference',side_effect=lambda role:{'path':role,'sha256':'a'*64}), \
                    patch.object(m.engine,'simulate_dynamic_frozen_execution_research',return_value={}) as engine, \
                    patch.object(m,'restore_and_audit',side_effect=ValueError('audit')):
                with self.assertRaisesRegex(ValueError,'audit'):m.run(output,True)
                failure=json.loads((output/'failure.json').read_bytes())
                with self.assertRaises(ValueError):m.recover(output,None,None)
                with patch.object(m,'restore_and_audit',return_value=({},{})):
                    m.recover(output,failure['started_reference']['sha256'],failure['raw_reference']['sha256'])
                self.assertEqual(engine.call_count,1)


if __name__=='__main__':unittest.main()
