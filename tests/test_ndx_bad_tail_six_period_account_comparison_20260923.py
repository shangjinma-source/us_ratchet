"""Synthetic risk-history and orchestration tests; no actual ledger audit."""
from copy import deepcopy
from decimal import Context,Decimal,localcontext
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_bad_tail_six_period_account_comparison_20260923 as m


def history_fixture():
    choices=[];rows=[];selected_maps={};union_maps={};previous=set();observed={};dates={};decisions=[];daily=[];fills=[]
    for i,(day,execution) in enumerate(m.CLOCK):
        selected={f'S{j}':dict(ticker=f'T{j}',issuer_id=f'I{j}',risk_chain=f'R{j}') for j in (range(4) if i==0 else range(1,5))}
        current={sid:v['risk_chain'] for sid,v in selected.items()};selected_maps[day]=current
        union_maps[day]={sid:'R'+sid[1:] for sid in set(selected)|previous};previous=set(selected)
        targets={sid:dict(ticker=v['ticker'],issuer_id=v['issuer_id'],target_weight=.25) for sid,v in selected.items()}
        rows.append(dict(decision_date=day,execution_date=execution,targets=targets))
        choices.append(dict(decision_date=day,execution_date=execution,saved_candidate={'selected':selected}))
        observed.update(current);dates.update({sid:day for sid in selected})
        before={} if i==0 else {'S0':10};union=set(before)|set(targets)
        status='NO_PLAN' if i in (2,3) else 'FROZEN'
        decisions.append(dict(decision_date=day,execution_date=execution,targets=targets,status=status,shares_before=before,
            risk_chains={sid:observed[sid] for sid in union},risk_chain_observation_dates={sid:dates[sid] for sid in union}))
        daily.append(dict(session=day,shares=before,risk_chains={sid:observed[sid] for sid in before},risk_chain_observation_dates={sid:dates[sid] for sid in before}))
        daily.append(dict(session=execution,shares={'S0':10},risk_chains={'S0':'R0'},risk_chain_observation_dates={'S0':m.CLOCK[0][0]}))
        if status=='FROZEN':fills.append(dict(session=execution,status='FILLED' if i==0 else 'REJECTED',shares_before=before,shares_after={'S0':10},cash_before_usd=100,cash_after_usd=100))
    return dict(schedule=rows,risk_chains_by_decision=union_maps),dict(saved_lane_choices=choices,selected_risk_chains_by_decision=selected_maps),dict(decisions=decisions,daily=daily,executions=fills,trades=[])


class ComparisonTests(unittest.TestCase):
    def test_multiple_no_plan_and_rejections_preserve_old_held_observation(self):
        schedule,projection,execution=history_fixture()
        maps,report=m.independent_risk_history(schedule,projection,execution)
        self.assertEqual(report['decision_count'],6);self.assertEqual(report['execution_count'],4)
        self.assertEqual(report['no_plan_count'],2);self.assertEqual(report['rejected_execution_count'],3)
        self.assertEqual(report['cutoff_evidence'][m.CLOCK[-1][0]]['observation_dates']['S0'],m.CLOCK[0][0])
        self.assertNotIn('S0',maps[m.CLOCK[-1][0]])

    def test_future_chain_and_no_plan_fake_execution_rejected(self):
        for attack in ('date','chain','no_plan_fill','rejected_trade'):
            schedule,projection,execution=history_fixture()
            if attack=='date':execution['daily'][-1]['risk_chain_observation_dates']['S0']=m.CLOCK[-1][0]
            if attack=='chain':execution['daily'][-1]['risk_chains']['S0']='future'
            if attack=='no_plan_fill':execution['executions'].insert(2,dict(session=m.CLOCK[2][1],status='REJECTED'))
            if attack=='rejected_trade':execution['trades'].append({'session':m.CLOCK[1][1]})
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.independent_risk_history(schedule,projection,execution)

    def test_candidate_single_normalization_and_single_accounting(self):
        schedule=json.loads((m.BASE/m.BOUND['schedule'][0]).read_bytes())
        projection=json.loads((m.BASE/m.BOUND['projection'][0]).read_bytes())
        labels={r['security_id']:r for r in projection['identity_projection']['rows']};calendar=projection['calendar']
        normalized,evidence=m.normalization.normalized_schedule(schedule['schedule'])
        conversion=[]
        for kind in ('open','close'):
            for day in calendar:
                for sid,label in labels.items():
                    value=projection['price_projection']['matrices'][kind][day][label['ticker']]
                    with localcontext(Context(prec=160)):error=abs(Decimal.from_float(float(value))-Decimal(value))
                    conversion.append(dict(session=day,security_id=sid,field=kind,original_decimal=value,execution_float=float(value),absolute_binary_float_error=str(error)))
        candidate=dict(calendar=calendar,schedule=schedule['schedule'],security_count=5,distinct_issuer_count=5,fixed_four_security_policy=False,
            per_decision_target_counts=[len(r['targets']) for r in schedule['schedule']],execution_contract=m.CONTRACT,
            normalized_schedule=normalized,normalization_evidence=evidence,risk_chain_evidence={},independent_decimal_accounting={'synthetic':True},
            execution={'daily':[{'total_value_usd':25000} for _ in calendar]},price_conversion_evidence=dict(
                policy='EXPLICIT_FLOAT_ONLY_AT_FROZEN_ENGINE_BOUNDARY_DECIMAL_MARKS_RETAINED_FOR_INDEPENDENT_AUDIT',cell_count=1070,cells=conversion))
        with patch.object(m,'independent_risk_history',return_value=({}, {'cutoff_evidence':{}})),patch.object(m.normalization,'normalized_schedule',wraps=m.normalization.normalized_schedule) as norm,patch.object(m.accounting,'audit',return_value={'synthetic':True}) as accounting:
            m.audit_candidate(candidate,schedule,projection)
            self.assertEqual(norm.call_count,1);self.assertEqual(accounting.call_count,1)
            for day,marks in accounting.call_args.kwargs['prices'].items():
                self.assertTrue(all(isinstance(r['open'],Decimal) for r in marks.values()))

    def test_external_candidate_and_output_directory_fail_closed(self):
        with self.assertRaises(ValueError):m.build(m.ACCOUNT_DIRECTORY/'account.json','0'*64,m.PRODUCER_SHA)
        with self.assertRaises(ValueError):m.publish({},m.ACCOUNT_DIRECTORY/'subdir'/'report.json')

    def test_metrics_107_not_295_and_nonfinite_rejected(self):
        self.assertEqual(m.metrics([100]*107)['path_return'],'0')
        for bad in ([100]*295,[True]*107,[float('nan')]*107):
            with self.assertRaises(ValueError):m.metrics(bad)


if __name__=='__main__':unittest.main()
