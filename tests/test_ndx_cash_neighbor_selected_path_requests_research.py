from copy import deepcopy
from datetime import date,timedelta
import unittest
from backtest import ndx_cash_neighbor_selected_path_requests_research as m
from backtest import ndx_cash_flow_return_accounting_research as accounting


def ref(name,pointer):return dict(path=name,sha256='a'*64,json_pointer=pointer)

def fixture():
    cases=[]
    for lane in m.LANES:
        for decision,execution,n in m.CLOCKS:
            for amount in ('1000','10000'):
                i=len(cases);sid=f'scenario-{i}';ids=['A','Z'];cash=str(1000+int(amount)-10.01);newcash=str(1000+int(amount)-20.02)
                flags=dict(orders_executed=False,point_in_time_verified=False,promotion_allowed=False)
                row=dict(scenario_id=sid,lane=lane,securities={'A':{'ticker':'AAA'},'Z':{'ticker':'ZZZ'}},holdings={'A':10,'Z':0},starting_cash_usd='1000',execution_prices={'A':'10','Z':'20'},transaction_cost_bps='10',cash_event=dict(decision_date=decision,execution_date=execution,amount_usd=amount),**flags)
                ir=ref('inputs',f'/rows/{i}');pr=ref('previous',f'/rows/{i}');planref=dict(pr,json_pointer=pr['json_pointer']+'/evaluation/branches/0/evaluated_plans/0')
                oldplan=dict(supplied_plan_index=0,buy_shares={'A':1,'Z':0},proposed_holdings={'A':11,'Z':0},gross_buy_usd='10',fees_usd='0.01',cash_after_usd=cash,feasible=True)
                domain=dict(conditional_research_buy_ids=ids,buy_limits={'A':20,'Z':20})
                c=dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_SCENARIO_CONTRACT_V1',rule='SAVED_NEIGHBOR_RULE',original_input_row=row,input_reference=ir,previous_result_reference=pr,conditional_research_buy_ids=ids,saved_buy_limits=domain['buy_limits'],original_selected_candidate_index=0,old_evaluated_points=[dict(candidate_index=0,buy_shares=oldplan['buy_shares'],saved_feasible=True,reference=planref)])
                prepared=dict(contract=c,contract_sha256=m.digest(c));base=ref('paired',f'/rows/{i}')
                days=[execution]+[(date(2023,9,1)-timedelta(days=j)).isoformat()for j in range(n-2,-1,-1)]if n>1 else [execution]
                initial=dict(session=decision,cash_usd='1000',holdings=deepcopy(row['holdings']),close_prices={'A':'10','Z':'20'})
                sessions=[dict(session=d,open_prices={'A':'10','Z':'20'},close_prices={'A':'10','Z':'20'},cash_injection_usd=amount if j==0 else '0',buy_shares=deepcopy(oldplan['buy_shares'])if j==0 else {})for j,d in enumerate(days)]
                template=dict(initial=initial,sessions=sessions,transaction_cost_bps='10')
                old=dict(scenario_id=sid,input_row=row,input_reference=ir,topup_context_reference=pr,topup_context=dict(input_row=row,domain=domain,selected_candidate_index=0),selected_plan=oldplan,selected_plan_reference=planref,security_to_ticker={'A':'AAA','Z':'ZZZ'},paths=dict(candidate=dict(accounting_inputs=template),same_flow_zero_trade_control=dict(accounting_inputs=dict(initial=deepcopy(initial)))),path_quote_evidence=[{'saved':'all source pointers and encodings'}],action_limits={'dividends_modelled':False},**flags)
                oldpath=dict(reference=dict(base,json_pointer=base['json_pointer']+'/paths/candidate'),scenario_id=sid,selected_candidate_index=0,buy_shares=oldplan['buy_shares'])
                newplan=dict(oldplan,buy_shares={'A':2,'Z':0},proposed_holdings={'A':12,'Z':0},gross_buy_usd='20',fees_usd='0.02',cash_after_usd=newcash)
                identity=dict(schema='CONDITIONAL_TOPUP_NEIGHBOR_TASK_IDENTITY_V1',rule=c['rule'],scenario_contract_sha256=prepared['contract_sha256'],buy_shares=newplan['buy_shares'])
                selected=dict(origin='NEW',identity=dict(task_id=m.digest(identity),identity=identity,scenario_id=sid),buy_shares=newplan['buy_shares'],saved_plan=newplan,feasible=True)
                s=dict(schema='CASH_NEIGHBOR_STREAM_SCENARIO_SELECTION_V1',scenario_id=sid,contract_sha256=prepared['contract_sha256'],selected=selected,status='NEW_PATH_REQUIRED',reused_path_reference=None,old_selected_path=oldpath,**flags)
                cases.append(dict(prepared=prepared,selection=s,old_paired_row=old,selection_reference=ref('selection',f'/cases/{i}'),selection_audit_reference=ref('audit',f'/cases/{i}'),old_paired_reference=base))
    return dict(cases=cases,expected_scenario_ids=[c['selection']['scenario_id']for c in cases])


class Tests(unittest.TestCase):
    def test_new_request_only_first_buy_changes_and_real_pure_account(self):
        args=fixture();before=deepcopy(args);out=m.prepare_selected_path_requests(**args);self.assertEqual(args,before);self.assertEqual(out['new_account_request_count'],40)
        r=out['rows'][0];request=r['accounting_request'];original=deepcopy(args['cases'][0]['old_paired_row']['paths']['candidate']['accounting_inputs']);original['sessions'][0]['buy_shares']={'A':2,'Z':0};self.assertEqual(request,original)
        account=accounting.account_path(**request)
        for key in ('gross_buy_usd','fees_usd','cash_after_usd'):self.assertEqual(m.number(account['rows'][0][key]),m.number(r['expected_first_trade'][key]))
        self.assertEqual(account['rows'][-1]['holdings_after'],{'A':12,'Z':0});self.assertEqual(r['old_paired_evidence'],before['cases'][0]['old_paired_row']);self.assertFalse(out['control_reexecuted'])

    def test_reuse_and_absence_never_dispatch(self):
        a=fixture();c=a['cases'][0];s=c['selection'];p=c['old_paired_row']['selected_plan'];s.update(status='REUSE_EXISTING_PAIRED_PATH',reused_path_reference=s['old_selected_path']['reference'],selected=dict(origin='OLD',identity={'old_candidate_index':0},buy_shares=p['buy_shares'],saved_plan=p,feasible=True))
        out=m.prepare_selected_path_requests(**a);self.assertEqual(out['status_counts'],{'REUSE_EXISTING_PAIRED_PATH':1,'NO_FEASIBLE_IN_DECLARED_UNION':0,'NEW_PATH_REQUIRED':39});self.assertIsNone(out['rows'][0]['accounting_request']);self.assertFalse(out['no_feasible_is_cash_return'])
        absent=deepcopy(a);absent['cases'][1]['selection'].update(selected=None,status='NO_FEASIBLE_IN_DECLARED_UNION')
        with self.assertRaisesRegex(ValueError,'contradicts'):m.prepare_selected_path_requests(**absent)
        s['reused_path_reference']=ref('foreign','/x')
        with self.assertRaises(ValueError):m.prepare_selected_path_requests(**a)

    def test_tampered_contract_quotes_zero_slots_order_and_plan_rejected(self):
        for mode in ('contract','zero','quote','laterbuy','order','oldpointer','holdings','authority','cap'):
            a=fixture();c=a['cases'][0];old=c['old_paired_row'];s=c['selection']
            if mode=='contract':c['prepared']['contract_sha256']='b'*64
            elif mode=='zero':del old['paths']['candidate']['accounting_inputs']['sessions'][1]['close_prices']['Z']
            elif mode=='quote':old['paths']['candidate']['accounting_inputs']['sessions'][0]['open_prices']['A']='11'
            elif mode=='laterbuy':old['paths']['candidate']['accounting_inputs']['sessions'][1]['buy_shares']={'A':1,'Z':0}
            elif mode=='order':a['expected_scenario_ids'].reverse()
            elif mode=='oldpointer':old['selected_plan_reference']=ref('previous','/rows/1')
            elif mode=='holdings':s['selected']['saved_plan']['proposed_holdings']['Z']=1
            elif mode=='authority':s['point_in_time_verified']=0
            else:s['selected']['saved_plan']['buy_shares']['A']=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.prepare_selected_path_requests(**a)

    def test_partial_forty_and_wrong_reuse_status_fail(self):
        a=fixture();a['cases'].pop()
        with self.assertRaises(ValueError):m.prepare_selected_path_requests(**a)
        a=fixture();a['cases'][0]['selection']['status']='REUSE_EXISTING_PAIRED_PATH'
        with self.assertRaises(ValueError):m.prepare_selected_path_requests(**a)

if __name__=='__main__':unittest.main()
