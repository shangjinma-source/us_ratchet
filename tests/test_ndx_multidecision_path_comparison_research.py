import unittest
from copy import deepcopy
from decimal import localcontext,Decimal
from fractions import Fraction
from test_ndx_multidecision_incumbent_inputs_research import fixture as sources
from backtest import ndx_multidecision_incumbent_inputs_research as inputs
from backtest import ndx_multidecision_path_comparison_research as m
from backtest.ndx_cash_fork_reference_window_research import metrics


def ref(name,pointer=''):return dict(path=name,sha256='a'*64,json_pointer=pointer)

def fixture():
    source=sources();candidate=source['candidate_evidence']['document']['inputs'];control=inputs.prepare_incumbent_account_inputs(**source)
    cal=control['rows'][0]['tracks'][0]['engine_binding']['keyword_arguments']['closes']['index']
    def slots(prepared,role):
        out=[]
        for li,lane in enumerate(prepared['rows']):
            for ti,t in enumerate(lane['tracks']):
                coord=[lane['fx_mode'],lane['lane'],t['track']];kw=t['engine_binding']['keyword_arguments'];pointer=ref(role,str('/rows/'+str(li*2+ti)+'/result'))
                if t['status'].startswith('BLOCKED'):
                    out.append(dict(coordinate=coord,outcome='BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT',reason='Original missing target',result=None,result_reference=None,audit_evidence=None,evidence_reference=ref(role,'/blocked')));continue
                daily=[dict(session=d,normalized_twr=1.,cash_injection_usd=0.,close_equity_usd=float(kw['initial_cash_usd']),total_value_usd=float(kw['initial_cash_usd'])) for d in cal]
                continuous=t['track']=='CONTINUOUS'
                r=dict(schema='DYNAMIC_FIXED_INCUMBENT_USD_FLOW_SPLIT_CONTROL_V1' if role=='control' else ('DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V2' if continuous else 'DYNAMIC_WHOLE_LOT_USD_FLOW_SPLIT_ACCOUNT_V1'),daily=daily,summary=dict(chained_twr=0.),external_flows=[],trades=[],point_in_time_verified=False,formal_benchmark_passed=False,promotion_allowed=False)
                if continuous:r.update(quantity_policy='FROZEN_PRIOR_CLOSE_TARGET_WEIGHTS_OPEN_CONTINUOUS_TWO_SIDED_FEE_SOLVE',cash_event_timing='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_REBALANCE_AND_FEES',**{k:float(kw[k]) for k in ('initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps')})
                else:r.update(execution_policy='DECISION_CLOSE_FROZEN_DELTA_NEXT_COMMON_SESSION_OPEN_ATOMIC_BASKET',flow_policy='ONLY_ALREADY_CREDITED_CASH_AVAILABLE_AT_DECISION_CLOSE',cash_event_timing='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_TRADES_AND_FEES')
                if role=='control':r.update(track=t['track'],weights_normalized=False,risk_is_order_gate=False,original_targets=deepcopy(kw['schedule'][0]['targets']))
                ins=dict(schema='MULTIDECISION_ACCOUNT_LEDGER_INSPECTION_V1' if role=='candidate' else 'MULTIDECISION_ORIGINAL_EIGHT_LEDGER_INSPECTION_V1',status='PASS',track=t['track'],daily_rows=len(cal),return_intervals=len(cal)-1,**dict.fromkeys(m.INSPECTION_FLAGS,False))
                out.append(dict(coordinate=coord,outcome=m.SUCCESS,reason=None,result=r,result_reference=pointer,evidence_reference=ref(role,'/post'),audit_evidence=dict(reference=ref(role,'/inspection'),reader_reference=ref(role+'reader'),result_reference=pointer,inspection=ins)))
        return out
    from test_ndx_same_window_nav_reference_metrics_research import fixture as nav_fixture,resign
    from backtest.ndx_multidecision_reference_metrics_research import reference_metrics
    args=nav_fixture();alignment=args['alignment'];template=alignment['rows'][0];alignment['session_dates']=cal;alignment['rows']=[]
    for d in cal:
        row=deepcopy(template);row['session']=d
        for conversion in row['conversions'].values():conversion.update(nav_date=d,fx_date=d,nav_usd_exact='1',nav_usd_decimal='1')
        alignment['rows'].append(row)
    resign(alignment);args['reference_calendar']['dates']=cal;nav=reference_metrics(**args)
    return dict(candidate_prepared=candidate,control_prepared=control,candidate_slots=slots(candidate,'candidate'),control_slots=slots(control,'control'),nav_metrics=nav,source_references={k:ref(k) for k in ('candidate_prepared','control_prepared','candidate_results','control_results','nav_metrics')})


class Tests(unittest.TestCase):
    def test_full_domain_blocked_and_nav_missing_preserve_other_paths(self):
        a=fixture();before=deepcopy(a);r=m.compare_multidecision_paths(**a);self.assertEqual(a,before);self.assertEqual(len(r['rows']),16);self.assertEqual(r['counts'],dict(candidate_metrics=8,control_metrics=16,missing_candidate=8));self.assertIsNone(r['rows'][0]['candidate']['metrics']);self.assertIsNotNone(r['rows'][0]['control']['metrics'])
        a['nav_metrics']['modes'][m.MODES[1]].update(status='BLOCKED_MISSING_REFERENCE_INPUT',metrics=None,missing_sessions=[r['calendar'][4]])
        r=m.compare_multidecision_paths(**a);self.assertIsNotNone(r['rows'][8]['candidate']['metrics']);self.assertIsNone(r['rows'][8]['distances']['candidate']);self.assertFalse(r['formal_comparison_passed'])
    def test_injection_not_return_initial_peak_drawdown_and_context(self):
        a=fixture();li=4;day=a['control_prepared']['rows'][li]['tracks'][0]['engine_binding']['keyword_arguments']['closes']['index'][1]
        f=dict(session=day,amount_usd=1000.,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='flow',sha256='a'*64))
        for key in ('candidate_prepared','control_prepared'):a[key]['rows'][li]['tracks'][0]['engine_binding']['keyword_arguments']['external_flows']=[f]
        for key in ('candidate_slots','control_slots'):
            r=a[key][8]['result'];r['external_flows']=[dict(event=f,event_id=m.hashlib.sha256(m.json.dumps(f,sort_keys=True,separators=(',',':')).encode()).hexdigest(),performance_boundary='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_REBALANCE')];r['daily'][1]['cash_injection_usd']=1000.
            for d in r['daily'][1:]:d['close_equity_usd']=26000.
        with localcontext() as c:
            c.prec=2;r=m.compare_multidecision_paths(**a)
        self.assertEqual(Decimal(r['rows'][8]['candidate']['metrics']['annualized_return_diagnostic_decimal']),0)
        for d in a['candidate_slots'][8]['result']['daily'][1:]:d['normalized_twr']=.5
        a['candidate_slots'][8]['result']['summary']['chained_twr']=-.5
        r=m.compare_multidecision_paths(**a);self.assertEqual(r['rows'][8]['candidate']['metrics']['maximum_drawdown'],dict(numerator='1',denominator='2'))
        self.assertEqual(r['rows'][8]['distances']['candidate_minus_control_absolute_distance']['maximum_drawdown'],'1/2')
    def test_full_calendar_source_and_flow_attacks(self):
        for attack in ('drop','mode','audit','flow','capital','mechanism'):
            a=fixture()
            if attack=='drop':a['candidate_slots'][8]['result']['daily'].pop(3)
            elif attack=='mode':a['candidate_slots'][8]['coordinate'][0]=m.MODES[0]
            elif attack=='audit':a['candidate_slots'][8]['audit_evidence']['result_reference']=ref('foreign')
            elif attack=='flow':a['candidate_slots'][8]['result']['daily'][1]['cash_injection_usd']=1.
            elif attack=='capital':a['control_prepared']['rows'][4]['tracks'][0]['engine_binding']['keyword_arguments']['initial_cash_usd']=1
            else:a['candidate_slots'][8]['result']['quantity_policy']='WHOLE'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.compare_multidecision_paths(**a)
    def test_technical_missing_is_not_cash_or_mode_fallback(self):
        a=fixture();s=a['candidate_slots'][8];s.update(outcome='NUMERICAL_EXCEPTION',reason='original exception',result=None,result_reference=None,audit_evidence=None)
        r=m.compare_multidecision_paths(**a);self.assertIsNone(r['rows'][8]['candidate']['metrics']);self.assertEqual(r['rows'][8]['candidate']['status'],'NUMERICAL_EXCEPTION');self.assertEqual(len(r['nav_modes_preserved']['modes']),2)

    def test_actual_prepared_engines_and_independent_inspectors_nonzero_flow(self):
        import pandas as pd
        import importlib
        from backtest.ndx_multidecision_account_inspection_research import inspect_saved_account
        from backtest.ndx_multidecision_incumbent_account_inspection_research import inspect_saved_control
        a=fixture()
        for ti in range(2):
            for role in ('candidate','control'):
                tr=a[role+'_prepared']['rows'][4]['tracks'][ti];kw=tr['engine_binding']['keyword_arguments']
                flow=dict(session=kw['closes']['index'][2],amount_usd=1000.,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='syntheticflow',sha256='a'*64))
                kw['external_flows']=[flow]
                if role=='candidate':tr['stateful_input']['external_flows']=[flow]
                restored=deepcopy(kw)
                for key in ('closes','opens'):
                    frame=restored[key];restored[key]=pd.DataFrame(frame['data'],index=pd.to_datetime(frame['index']),columns=frame['columns'])
                module=importlib.import_module(tr['engine_binding']['source_reference']['path'].replace('/','.').removesuffix('.py'))
                result=getattr(module,tr['engine_binding']['function'])(**restored)
                inspection=(inspect_saved_account if role=='candidate' else inspect_saved_control)(prepared_track=tr,result=result)
                slot=a[role+'_slots'][8+ti];slot['result']=result;slot['audit_evidence']['inspection']=inspection
        r=m.compare_multidecision_paths(**a)
        self.assertEqual(len(r['rows']),16)
        for ti in range(2):
            for role in ('candidate','control'):self.assertIsNotNone(r['rows'][8+ti][role]['metrics'])

if __name__=='__main__':unittest.main()

