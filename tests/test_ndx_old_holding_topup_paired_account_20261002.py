from copy import deepcopy
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backtest.ndx_cash_flow_return_accounting_research import account_path
from scripts import ndx_old_holding_topup_paired_account_20261002 as module


def pair_fixture():
    refs={role:{'path':'synthetic/'+role,'sha256':'a'*64} for role in module.PINS}
    row={'scenario_id':'synthetic','lane':'RETURN','branch_role':'MAIN_LANE','holdings':{'A':10,'C':0},
        'starting_cash_usd':'100','transaction_cost_bps':'10','cash_event':{'decision_date':'2023-08-31','execution_date':'2023-09-01','amount_usd':'1000'},
        'securities':{sid:{'ticker':sid,'issuer_id':sid,'risk_chain':sid} for sid in 'ABC'},
        'execution_prices':dict.fromkeys('ABC','20'),'gaps':['synthetic unresolved']}
    plan={'supplied_plan_index':0,'feasible':True,'buy_shares':{'A':0,'B':5,'C':0},
        'proposed_holdings':{'A':10,'B':5,'C':0},'gross_buy_usd':'100','fees_usd':'.1','cash_after_usd':'999.9'}
    days=['2023-08-31','2023-09-01']
    projection={'tickers':list('ABC'),'matrices':{field:{day:dict.fromkeys('ABC','10' if day==days[0] else '20.0000') for day in days} for field in ('open','close')}}
    control={ticker:{day:(index,{'session':day,'ticker':ticker,'currency':'USD','nominal_open':10.0 if index==0 else 20.0,'nominal_close':10.0 if index==0 else 20.0}) for index,day in enumerate(days)} for ticker in 'AC'}
    return row,plan,days,projection,control,refs


def document_fixture():
    row,plan,_,_,_,refs=pair_fixture()
    calendar=['2023-03-31']+[(date(2023,4,3)+timedelta(days=i)).isoformat() for i in range(105)]+['2023-09-01']
    flags=dict.fromkeys(('orders_executed','point_in_time_verified','promotion_allowed'),False)
    docs={'inputs':dict(schema='REMAINING_STANDARD_CASH_INPUTS_V1',rows=[],source_hashes={},**flags),
          'topups':dict(schema='OLD_HOLDING_TOPUP_CONDITIONAL_RESEARCH_V1',rows=[],source_hashes={},**flags)}
    for lane,schema in module.PRICE_SCHEMAS.items():
        price={'tickers':list('ABC'),'channels':[{'all_returned_raw_events':{'dividends':'not paid'}}],
               'matrices':{field:{day:dict.fromkeys('ABC','20') for day in calendar} for field in ('open','close')}}
        doc=dict(schema=schema,calendar=calendar,corporate_action_completeness_verified=False,dividend_cash_flows_modelled=False,
            point_in_time_verified=False,promotion_allowed=False)
        if lane in ('BAD_TAIL','DRAWDOWN'): doc['price_projection']=price
        else: doc.update(price)
        docs[lane+'_price']=doc
        for decision,execution,_ in module.CLOCKS:
            for amount in ('1000','10000'):
                index=len(docs['inputs']['rows']); item=deepcopy(row)
                item.update(lane=lane,scenario_id=str(index),cash_event=dict(decision_date=decision,execution_date=execution,amount_usd=amount))
                docs['inputs']['rows'].append(item)
                docs['topups']['rows'].append({'scenario_id':str(index),'input_row':deepcopy(item),
                    'input_reference':module.pointer(refs['inputs'],f'/rows/{index}'),'selected_candidate_index':0,
                    'evaluation':{'branches':[{'branch_id':str(index),'evaluated_plans':[deepcopy(plan)]}]},
                    'assumption':'retained synthetic','closure_records':[],'feasible_scores':[]})
    docs['inputs']['rows'] += [{'scenario_id':'control'+str(i)} for i in range(24)]
    docs['control']={'schema':'ndx_incumbent_nominal_control_research_v1','execution':{'old':'not replayed'},
        'nominal_quotes':{'by_ticker':{}},'dividends_modelled':False,'price_identity_binding_verified':False,
        'point_in_time_verified':False,'promotion_allowed':False}
    return docs,refs


class PairedTests(unittest.TestCase):
    def test_overnight_gain_same_flow_fee_and_all_zero_keys(self):
        row,plan,days,projection,control,refs=pair_fixture()
        result=module.calculate_pair(row,plan,days,projection,'',control,refs,account_path)
        candidate=result['paths']['candidate']; baseline=result['paths']['same_flow_zero_trade_control']
        self.assertEqual(module.from_ratio(baseline['account']['chained_twr']),Fraction(1,2))
        self.assertEqual(module.from_ratio(candidate['account']['chained_twr']),Fraction(3,2)*Fraction(12999,13000)-1)
        self.assertEqual(candidate['account']['rows'][0]['holdings_after'],{'A':10,'B':5,'C':0})
        self.assertEqual(baseline['account']['rows'][0]['holdings_after'],{'A':10,'C':0})
        self.assertEqual(baseline['account']['total_fees_usd'],'0')
        self.assertEqual(candidate['accounting_inputs']['sessions'][0]['open_prices']['C'],'20.0000')
        self.assertEqual(result['path_quote_evidence'][0]['open']['A']['chosen_observation_index'],0)
        self.assertEqual(len(result['path_quote_evidence'][0]['open']['A']['observations']),2)
        self.assertEqual(candidate['accounting_inputs']['initial'],baseline['accounting_inputs']['initial'])

    def test_intersection_conflict_currency_and_zero_sid_missing_fail(self):
        row,plan,days,projection,control,refs=pair_fixture()
        control['A'][days[1]][1]['nominal_open']=21.0
        with self.assertRaisesRegex(ValueError,'conflict'): module.calculate_pair(row,plan,days,projection,'',control,refs,account_path)
        row,plan,days,projection,control,refs=pair_fixture(); del projection['matrices']['close'][days[1]]['C']
        with self.assertRaises(KeyError): module.calculate_pair(row,plan,days,projection,'',control,refs,account_path)
        row,plan,days,projection,control,refs=pair_fixture(); control['A'][days[0]][1]['currency']='EUR'
        with self.assertRaisesRegex(ValueError,'USD'): module.calculate_pair(row,plan,days,projection,'',control,refs,account_path)

    def test_selected_exact_input_and_bool_refusal(self):
        docs,refs=document_fixture(); item=docs['topups']['rows'][0]; row=docs['inputs']['rows'][0]
        index,plan=module.selected_plan(item,row); self.assertEqual(index,0)
        item['selected_candidate_index']=False
        with self.assertRaises(ValueError): module.selected_plan(item,row)
        item['selected_candidate_index']=0; item['input_row']['holdings']['A']=11
        with self.assertRaisesRegex(ValueError,'input row'): module.selected_plan(item,row)

    def test_exact40_metadata_preserved_and_duplicate_coordinate_rejected(self):
        docs,refs=document_fixture()
        with patch.object(module,'calculate_pair',return_value={'synthetic_pair':True}) as calculate:
            result=module.assemble(docs,refs,Mock())
            self.assertEqual(calculate.call_count,40); self.assertEqual(result['new_account_path_count'],80)
            self.assertEqual(result['rows'][0]['input_row']['gaps'],['synthetic unresolved'])
            self.assertEqual(result['rows'][0]['topup_context']['assumption'],'retained synthetic')
            self.assertEqual(result['price_evidence_metadata']['RETURN']['channels'],docs['RETURN_price']['channels'])
            self.assertFalse(result['annualized_return_calculated'])
        docs['topups']['rows'][1]=deepcopy(docs['topups']['rows'][0])
        with patch.object(module,'calculate_pair',return_value={}):
            with self.assertRaisesRegex(ValueError,'unique'): module.assemble(docs,refs,Mock())

    def test_first_cash_reconciliation_and_injected_control_trade_rejected(self):
        row,plan,days,projection,control,refs=pair_fixture(); plan['cash_after_usd']='999'
        with self.assertRaisesRegex(ValueError,'Fixed cash'): module.calculate_pair(row,plan,days,projection,'',control,refs,account_path)
        row,plan,days,projection,control,refs=pair_fixture(); calls=[]
        def tamper(**kwargs):
            result=account_path(**kwargs); calls.append(1)
            if len(calls)==2: result['rows'][0]['buy_shares']={'A':1}
            return result
        with self.assertRaisesRegex(ValueError,'Unexpected trade'): module.calculate_pair(row,plan,days,projection,'',control,refs,tamper)

    def test_receipt_source_drift_failure_no_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); source=base/'source.py'; source.write_text('synthetic'); pins={}
            for role,publication,name,schema,status,refkey in [('inputs','input_publication','inputs.json','REMAINING_STANDARD_CASH_INPUTS_PUBLICATION_V1','INPUTS_ONLY_NOT_EXECUTED','input_reference'),('topups','topup_publication','results.json','OLD_HOLDING_TOPUP_PUBLICATION_V1','PUBLISHED_CONDITIONAL_TOPUPS_ONLY','result_reference')]:
                folder=base/role; folder.mkdir(); path=folder/name; path.write_bytes(module.encode({'source_hashes':{}}))
                pins[role]=(str(path),module.sha(path.read_bytes()))
                receipt={'schema':schema,'status':status,refkey:{'path':str(path),'sha256':pins[role][1]},'source_hashes':{},
                    **dict.fromkeys(('orders_executed','point_in_time_verified','promotion_allowed','fork_executable'),False)}
                rp=folder/'publication.json'; rp.write_bytes(module.encode(receipt)); pins[publication]=(str(rp),module.sha(rp.read_bytes()))
                if role=='topups': (folder/'started.json').write_text('{}')
            output=base/'new'; original=module.write_new
            def drift(path,value):
                digest=original(path,value)
                if path.name=='publication.json': source.write_text('drift')
                return digest
            with patch.object(module,'SOURCE',source),patch.object(module,'LOADED_SHA',module.sha(source.read_bytes())),patch.object(module,'PINS',pins),patch.object(module,'OUTPUT',output),patch.object(module,'assemble',return_value={'synthetic':True}),patch.object(module,'load_account_path',return_value=Mock()),patch.object(module,'write_new',side_effect=drift):
                with self.assertRaisesRegex(ValueError,'Source drift'): module.run()
                self.assertTrue((output/'failure.json').exists())
                with self.assertRaisesRegex(ValueError,'namespace exists'): module.run()


if __name__=='__main__':
    unittest.main()
