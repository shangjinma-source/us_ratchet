from copy import deepcopy
from datetime import date,timedelta
import unittest
from backtest import ndx_dated_account_input_research as core

REF={'path':'saved.json','sha256':'a'*64}
def dates(start,end):
    out=[];d=date.fromisoformat(start)
    while d<=date.fromisoformat(end):
        if d.weekday()<5:out.append(d.isoformat())
        d+=timedelta(days=1)
    return out

def fixture():
    before=dates('2025-09-01','2026-03-19')[-126:]
    after=dates('2026-03-23','2026-09-21')
    keep={'2026-04-06','2026-06-12',after[0],after[-1]}
    while len(after)>126:after.remove(next(x for x in after[1:-1] if x not in keep))
    calendar=before+['2026-03-20']+after
    selected={'security:1:BKNG':dict(ticker='BKNG',issuer_id='issuer:1',risk_chain='travel'),'security:2:KLAC':dict(ticker='KLAC',issuer_id='issuer:2',risk_chain='semi')}
    def channel(ticker):
        policies=[]
        if ticker in ('BKNG','KLAC'):policies=[dict(session='2026-04-06' if ticker=='BKNG' else '2026-06-12',kind='ORDINARY_SPLIT',numerator=25 if ticker=='BKNG' else 10,denominator=1)]
        return dict(ticker=ticker,status='CONDITIONAL_NUMERIC_RESULT',conditional_reconstruction_performed=True,provider_price_unit_assumption=core.UNIT,calendar=calendar,training_freeze_close_date='2026-03-20',quote_rows=[dict(session=d,nominal_open_exact='100',nominal_close_exact='101') for d in calendar],event_policies=policies,returned_events={'dividends':{'old':'preserved'}})
    candidate={s:channel(r['ticker']) for s,r in selected.items()}
    incumbent=[dict(security_id='security:incumbent_overlay:TSM' if i==0 else f'security:{i+10}:T{i}',ticker='TSM' if i==0 else f'T{i}',issuer_id=f'issuer:{i+10}',risk_chain='chain',target_weight=.12500000000000003) for i in range(8)]
    control={r['security_id']:channel(r['ticker']) for r in incumbent}
    identity=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff='2026-03-20',requested_previous_target_weights=None,selected=selected,holding_count=2,parameters=deepcopy(core.PARAMETERS),fit_data_sha256='b'*64,weight_spec='equal_weight',fitter_source_fingerprint=core.digest({'fitter':'c'*64}))
    location={'schema':'DATED_FIXED_CONSTITUENT_TASK_LOCATION_V1'}
    task=dict(numerical_identity=identity,numerical_task_id=core.digest(identity),location_identity=location,location_id=core.digest(location))
    fit=dict(schema='ndx_dynamic_cutoff_refit_research_v2',cutoff='2026-03-20',fit_data_sha256='b'*64,weight_spec='equal_weight',previous_target_weights={},source_hashes={'fitter':'c'*64},targets={s:dict(ticker=r['ticker'],issuer_id=r['issuer_id'],target_weight=.5) for s,r in selected.items()},declared_constraint_checks={'MINIMUM_EFFECTIVE_N':False})
    evidence={s:[] for s in set(candidate)|set(control)}
    for s,c in candidate.items():
        p=c['event_policies'][0];evidence[s]=[dict(event=dict(security_id=s,session=p['session'],new_shares=p['numerator'],old_shares=1,source_url='https://saved.example/notice',evidence_sha256='d'*64),policy_reference=dict(REF,json_pointer='/event/0'))]
    return dict(task=task,fit_result=fit,task_reference=REF,fit_reference=REF,candidate_channels_by_security=candidate,incumbent_securities=incumbent,incumbent_channels_by_security=control,channel_references={s:dict(REF,json_pointer='/rows/'+str(i)+'/channel') for i,s in enumerate(sorted(evidence))},split_evidence_by_security=evidence)

class Tests(unittest.TestCase):
    def test_split_events_no_double_adjust_control_original_weights(self):
        args=fixture();original=deepcopy(args);result=core.assemble_dated_account_inputs(**args)
        self.assertEqual(args,original);self.assertEqual(len(result['calendar']),127)
        self.assertEqual([e['new_shares'] for e in result['candidate']['corporate_actions']],[25,10])
        self.assertEqual(result['candidate']['matrices']['open']['data'][0],[100.,100.])
        self.assertEqual(result['incumbent']['original_security_order'],[r['security_id'] for r in args['incumbent_securities']])
        self.assertEqual([t['target_weight'] for t in result['incumbent']['schedule'][0]['targets'].values()],[.12500000000000003]*8)
        self.assertFalse(result['incumbent']['risk_observation_gates_orders']);self.assertFalse(result['split_evidence_authenticated'])
    def test_frozen_candidate_and_control_execute_nominal_splits(self):
        import pandas as pd
        from backtest import ndx_dynamic_frozen_execution_research as engine
        from backtest import ndx_dynamic_frozen_incumbent_control as control_engine
        a=fixture();selected=a['task']['numerical_identity']['selected']
        for i in (3,4):
            sid=f'security:{i}:T{i}'
            selected[sid]=dict(ticker=f'T{i}',issuer_id=f'issuer:{i}',risk_chain=f'chain{i}')
            c=deepcopy(next(iter(a['incumbent_channels_by_security'].values())));c['ticker']=f'T{i}'
            a['candidate_channels_by_security'][sid]=c
            a['channel_references'][sid]=dict(REF,json_pointer=f'/extra/{i}')
            a['split_evidence_by_security'][sid]=[]
            a['fit_result']['targets'][sid]=dict(ticker=f'T{i}',issuer_id=f'issuer:{i}',target_weight=.25)
        a['task']['numerical_identity']['holding_count']=4
        for target in a['fit_result']['targets'].values():target['target_weight']=.25
        a['task']['numerical_task_id']=core.digest(a['task']['numerical_identity'])
        for channel in list(a['candidate_channels_by_security'].values())+list(a['incumbent_channels_by_security'].values()):
            for row in channel['quote_rows']:
                value=core.Fraction(100)
                for policy in channel['event_policies']:
                    if row['session']>=policy['session']:value/=policy['numerator']
                row['nominal_open_exact']=row['nominal_close_exact']=str(value)
        assembled=core.assemble_dated_account_inputs(**a)
        def execute(account,fn):
            kwargs={k:account[k] for k in ('schedule','risk_chains_by_decision','corporate_actions','initial_cash_usd','minimum_cash_buffer_usd','valuation_end_date','transaction_cost_bps','identity_events')}
            for target,field in [('opens','open'),('closes','close')]:
                matrix=account['matrices'][field]
                kwargs[target]=pd.DataFrame(matrix['data'],index=pd.to_datetime(matrix['index']),columns=matrix['columns'])
            if account['role']=='incumbent':kwargs.pop('identity_events')
            return fn(**kwargs,**account['risk_parameters'])
        result=execute(assembled['candidate'],engine.simulate_dynamic_frozen_execution_research)
        control=execute(assembled['incumbent'],control_engine.simulate_dynamic_frozen_incumbent_control)
        self.assertTrue(result['trades']);self.assertTrue(control['trades'])
        first=result['daily'][1]['shares'];last=result['daily'][-1]['shares']
        for sid,multiple in [('security:1:BKNG',25),('security:2:KLAC',10)]:
            self.assertGreater(first[sid],0);self.assertEqual(last[sid],first[sid]*multiple)
        self.assertAlmostEqual(result['daily'][1]['total_value_usd'],result['daily'][-1]['total_value_usd'])
        self.assertEqual(len(result['corporate_actions']),2)
        self.assertEqual(set(first),set(selected))
        self.assertEqual(set(control['daily'][-1]['shares']),{r['security_id'] for r in a['incumbent_securities']})

    def test_split_omission_ratio_and_double_adjust_input_rejected(self):
        for attack in ('omit','ratio','unit'):
            a=fixture();sid=next(iter(a['candidate_channels_by_security']))
            if attack=='omit':a['split_evidence_by_security'][sid]=[]
            if attack=='ratio':a['split_evidence_by_security'][sid][0]['event']['new_shares']=1
            if attack=='unit':a['candidate_channels_by_security'][sid]['provider_price_unit_assumption']='ALREADY_ADJUSTED_CLOSE'
            with self.subTest(attack=attack),self.assertRaises(ValueError):core.assemble_dated_account_inputs(**a)
    def test_calendar_missing_reordered_and_wrong_cutoff(self):
        for attack in ('missing','reordered','oldcutoff','prior'):
            a=fixture();c=next(iter(a['candidate_channels_by_security'].values()))
            if attack=='missing':c['quote_rows'].pop(127)
            if attack=='reordered':c['quote_rows'][126:128]=reversed(c['quote_rows'][126:128])
            if attack=='oldcutoff':a['task']['numerical_identity']['cutoff']='2026-09-21'
            if attack=='prior':a['task']['numerical_identity']['requested_previous_target_weights']={}
            with self.subTest(attack=attack),self.assertRaises(ValueError):core.assemble_dated_account_inputs(**a)
    def test_zero_weight_preserved_and_bad_coordinates_bool_rejected(self):
        a=fixture();sid=list(a['fit_result']['targets']);a['fit_result']['targets'][sid[0]]['target_weight']=0;a['fit_result']['targets'][sid[1]]['target_weight']=1
        result=core.assemble_dated_account_inputs(**a);self.assertEqual(len(result['candidate']['matrices']['open']['columns']),2)
        self.assertEqual(result['candidate']['engine_input_status'],'BLOCKED_ZERO_TARGET_WEIGHT')
        self.assertTrue(result['candidate']['engine_dispatch_blockers'])
        a['fit_result']['targets'][sid[0]]['target_weight']=False
        with self.assertRaises(ValueError):core.assemble_dated_account_inputs(**a)

if __name__=='__main__':unittest.main()
