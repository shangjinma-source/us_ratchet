from copy import deepcopy
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backtest.ndx_cash_flow_return_accounting_research import account_path
from scripts import ndx_first_period_cash_buy_hold_account_20261002 as module


def fixture():
    refs={role:{'path':'synthetic/'+role,'sha256':'a'*64} for role in module.PINS}
    flags=dict.fromkeys(('orders_executed','point_in_time_verified','promotion_allowed'),False)
    inputs=dict(schema='FIRST_PERIOD_STANDARD_CASH_INPUTS_V1',rows=[],source_hashes={},**flags)
    repair=dict(schema='FIRST_PERIOD_CASH_REPAIR_RESEARCH_V1',rows=[],source_hashes={},**flags)
    old=dict(schema='FIRST_PERIOD_CASH_NEIGHBOR_RESEARCH_V1',rows=[],source_hashes={},**flags)
    calendar=['2023-03-31']+[(date(2023,4,3)+timedelta(days=i)).isoformat() for i in range(105)]+['2023-09-01']
    docs={'inputs':inputs,'repair_results':repair,'old_results':old}
    for lane,schema in module.PRICE_SCHEMAS.items():
        price=dict(tickers=list('ABCD'),channels=[{'ticker':'A','all_returned_raw_events':{'dividends':{'example':'preserved not paid'}}}],
            matrices={field:{day:dict.fromkeys('ABCD','10') for day in calendar} for field in ('open','close')})
        doc=dict(schema=schema,calendar=calendar,corporate_action_completeness_verified=False,
            dividend_cash_flows_modelled=False,point_in_time_verified=False,promotion_allowed=False,source_hashes={})
        if lane in ('BAD_TAIL','DRAWDOWN'): doc['price_projection']=price
        else: doc.update(price)
        docs[lane+'_price']=doc
        for amount in ('1000','10000'):
            index=len(inputs['rows']); scenario=lane+'|'+amount
            row=dict(scenario_id=scenario,lane=lane,holdings={},starting_cash_usd='25000',transaction_cost_bps='10',
                cash_event=dict(decision_date='2023-03-31',execution_date='2023-04-03',amount_usd=amount),
                target_weights=dict.fromkeys('ABCD','.25'),execution_prices=dict.fromkeys('ABCD','10'),
                securities={sid:{'ticker':sid,'issuer_id':sid,'risk_chain':sid} for sid in 'ABCD'},gaps=['synthetic retained'])
            plan=dict(supplied_plan_index=0,feasible=True,buy_shares=dict.fromkeys('ABCD',100),
                proposed_holdings=dict.fromkeys('ABCD',100),fees_usd='4',gross_buy_usd='4000',cash_after_usd=str(25000+int(amount)-4004))
            evaluation={'branches':[{'branch_id':scenario,'evaluated_plans':[deepcopy(plan)]}]}
            source='PREVIOUS_BATCH' if lane in ('BAD_TAIL','LEGACY_TARGET_DISTANCE') and amount=='1000' else 'NEW_REPAIR_BATCH'
            previous=dict(scenario_id=scenario,evaluation=deepcopy(evaluation))
            repaired=dict(scenario_id=scenario,evaluation=deepcopy(evaluation),
                input_reference=module.pointer(refs['inputs'],f'/rows/{index}'),
                previous_result_reference=module.pointer(refs['old_results'],f'/rows/{index}'),
                selected={'source':source,'plan_index':0,'fee_usd':{'numerator':'4','denominator':'1'}})
            # Nonselected saved branch intentionally disagrees; it must never route here.
            nonselected=previous if source=='NEW_REPAIR_BATCH' else repaired
            nonselected['evaluation']['branches'][0]['evaluated_plans'][0]['fees_usd']='999'
            inputs['rows'].append(row); old['rows'].append(previous); repair['rows'].append(repaired)
    return docs,refs


class BuyHoldTests(unittest.TestCase):
    def test_source_routes_one_flow_and_fee_including_initial_drawdown(self):
        docs,refs=fixture(); wrapped=Mock(wraps=account_path)
        result=module.assemble(docs,refs,wrapped)
        self.assertEqual(wrapped.call_count,8)
        self.assertEqual(sum(len(row['account']['rows']) for row in result['rows']),848)
        for index,row in enumerate(result['rows']):
            amount=int(row['input_row']['cash_event']['amount_usd']); expected=Fraction(-4,25000+amount)
            self.assertEqual(module.from_ratio(row['account']['chained_twr']),expected)
            self.assertEqual(module.from_ratio(row['drawdown']['maximum_drawdown']),-expected)
            self.assertEqual(row['account']['total_fees_usd'],'4')
            self.assertEqual(row['account']['rows'][-1]['holdings_after'],dict.fromkeys('ABCD',100))
            self.assertEqual(row['accounting_inputs']['initial']['close_prices'],{})
            self.assertEqual(row['accounting_inputs']['sessions'][1]['buy_shares'],{})
            role='old_results' if index in (2,6) else 'repair_results'
            self.assertEqual(row['selected_plan_reference']['path'],refs[role]['path'])
        self.assertEqual(result['price_evidence_metadata']['RETURN']['channels'], docs['RETURN_price']['channels'])
        self.assertFalse(result['total_return_claimed'])

    def test_first_open_literal_and_selection_bool_fail_closed(self):
        docs,refs=fixture(); docs['RETURN_price']['matrices']['open']['2023-04-03']['A']='10.0'
        with self.assertRaisesRegex(ValueError,'First Open literal'): module.assemble(docs,refs,account_path)
        docs,refs=fixture(); docs['repair_results']['rows'][0]['selected']['plan_index']=False
        with self.assertRaisesRegex(ValueError,'Selected index'): module.assemble(docs,refs,account_path)
        docs,refs=fixture(); docs['repair_results']['rows'][0]['evaluation']['branches'][0]['evaluated_plans'][0]['feasible']=1
        with self.assertRaisesRegex(ValueError,'must be feasible'): module.assemble(docs,refs,account_path)

    def test_missing_or_nonfinite_mark_and_calendar_mismatch_rejected(self):
        docs,refs=fixture(); del docs['RETURN_price']['matrices']['close']['2023-04-04']['D']
        with self.assertRaises(KeyError): module.assemble(docs,refs,account_path)
        docs,refs=fixture(); docs['RETURN_price']['matrices']['close']['2023-04-04']['D']='NaN'
        with self.assertRaises(ValueError): module.assemble(docs,refs,account_path)
        docs,refs=fixture(); docs['DRAWDOWN_price']['calendar']=list(docs['DRAWDOWN_price']['calendar']); docs['DRAWDOWN_price']['calendar'][4]='2023-04-03'
        with self.assertRaises(ValueError): module.assemble(docs,refs,account_path)

    def test_duplicate_scenario_and_initial_or_fee_reconciliation_rejected(self):
        docs,refs=fixture(); docs['inputs']['rows'][1]['cash_event']['amount_usd']='1000'
        with self.assertRaisesRegex(ValueError,'denominator'): module.assemble(docs,refs,account_path)
        docs,refs=fixture(); docs['inputs']['rows'][0]['holdings']={'A':1}
        with self.assertRaisesRegex(ValueError,'initial'): module.assemble(docs,refs,account_path)
        docs,refs=fixture(); docs['repair_results']['rows'][0]['evaluation']['branches'][0]['evaluated_plans'][0]['cash_after_usd']='21995'
        with self.assertRaisesRegex(ValueError,'reconciliation'): module.assemble(docs,refs,account_path)

    def test_drawdown_peak_includes_initial_one(self):
        account={'rows':[{'cumulative_twr':module.rational(Fraction(-1,10))},
                         {'cumulative_twr':module.rational(Fraction(1,5))},
                         {'cumulative_twr':module.rational(Fraction(-1,10))}]}
        self.assertEqual(module.from_ratio(module.maximum_drawdown(account)['maximum_drawdown']),Fraction(1,4))

    def test_post_receipt_drift_failure_and_no_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); source=base/'source.py'; source.write_text('synthetic')
            pins={}; source_docs={}
            for role,names in [('inputs',('inputs.json','publication.json')),('old_results',('results.json','started.json')),('repair_results',('results.json','started.json'))]:
                folder=base/role; folder.mkdir()
                for name in names: (folder/name).write_bytes(module.encode({'source_hashes':{}}))
                path=folder/names[0]; pins[role]=(str(path),module.sha(path.read_bytes()))
            input_ref={'path':pins['inputs'][0],'sha256':pins['inputs'][1]}
            receipt=base/'inputs/publication.json'
            receipt.write_bytes(module.encode({'schema':'FIRST_PERIOD_STANDARD_CASH_INPUTS_PUBLICATION_V1',
                'input_reference':input_ref,'source_hashes':{},'status':'INPUTS_ONLY_NOT_EXECUTED',
                **dict.fromkeys(('cash_fork_called','orders_executed','point_in_time_verified','promotion_allowed','fork_executable'),False)}))
            pins['input_publication']=(str(receipt),module.sha(receipt.read_bytes()))
            output=base/'new'; original=module.write_new
            def drift(path,value):
                digest=original(path,value)
                if path.name=='publication.json': source.write_text('tampered')
                return digest
            with patch.object(module,'SOURCE',source),patch.object(module,'LOADED_SHA',module.sha(source.read_bytes())),patch.object(module,'OUTPUT',output),patch.object(module,'PINS',pins),patch.object(module,'load_account_path',return_value=Mock()),patch.object(module,'assemble',return_value={'synthetic':True}),patch.object(module,'write_new',side_effect=drift):
                with self.assertRaisesRegex(ValueError,'Source drift'): module.run()
                self.assertTrue((output/'failure.json').exists())
                with self.assertRaisesRegex(ValueError,'namespace exists'): module.run()


if __name__=='__main__':
    unittest.main()
