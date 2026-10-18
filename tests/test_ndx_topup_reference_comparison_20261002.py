from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from scripts import ndx_topup_reference_comparison_20261002 as module


def fixture():
    days=[]; current=date(2023,3,31)
    holidays={'2023-04-07','2023-05-29','2023-06-19','2023-07-04'}
    while current<=date(2023,9,1):
        if current.weekday()<5 and current.isoformat() not in holidays: days.append(current.isoformat())
        current+=timedelta(days=1)
    refs={role:{'path':'synthetic/'+role,'sha256':'a'*64} for role in module.PINS}
    authority={'point_in_time_verified':False,'promotion_allowed':False}
    benchmark=dict(schema='RETURN_SIX_PERIOD_REUSED_BENCHMARK_PREFIX_V1',calendar=days,
        formal_dual_benchmark_admission=False,execution_rerun=False,**authority,
        incumbent={'daily':[{'session':day,'total_value_usd':100.0+index} for index,day in enumerate(days)]},
        nav={'rows':[{'session':day,'nav_date':day,'nav':2.0+index/100} for index,day in enumerate(days)],
             'publication_time_verified':False,'currency_fx_equivalence_verified':False,'subscription_redemption_fee_equivalence_verified':False})
    currency=dict(schema='FUND_CURRENCY_ISSUER_LISTING_CAPTURE_V1',fund_code='012922',currency='CNY',source_reference=refs['currency_html'],
        **dict.fromkeys(('nav_dataset_currency_binding_certified','historical_2023_class_continuity_verified','fx_rates_supplied',
                        'point_in_time_verified','promotion_allowed','subscription_terms_verified'),False))
    accounts=dict(schema='OLD_HOLDING_TOPUP_PAIRED_PRICE_ONLY_ACCOUNT_V1',scenario_count=40,rows=[],observed_calendar=days,**authority)
    for lane in module.LANES:
        for decision,execution,_ in module.CLOCKS:
            observed=days[days.index(decision)+1:]
            for amount in ('1000','10000'):
                index=len(accounts['rows']); event=dict(decision_date=decision,execution_date=execution,amount_usd=amount)
                initial={'session':decision,'cash_usd':'100','holdings':{'X':1},'close_prices':{'X':'20'}}
                path={'accounting_inputs':{'initial':initial},'account':{'cash_event_timing':'AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_BUYS_AND_FEES',
                    'rows':[{'session':day,'cumulative_twr':{'numerator':str(j),'denominator':'100'},
                        'cash_injection_usd':amount if j==0 else '0','close_equity_usd':'999999999'} for j,day in enumerate(observed)]}}
                accounts['rows'].append({'scenario_id':str(index),'input_row':{'scenario_id':str(index),'lane':lane,'cash_event':event,'gaps':['kept']},
                    'paths':{'candidate':deepcopy(path),'same_flow_zero_trade_control':deepcopy(path)},
                    'topup_context':{'scope':'synthetic'},'selected_plan_reference':{'path':'frozen'}})
    return {'accounts':accounts,'benchmark':benchmark,'currency_manifest':currency},refs


def mock_compare(**kwargs):
    return {'schema':'CASH_FORK_FOUR_ROLE_EXACT_REFERENCE_WINDOW_V1',
        'calendar':[kwargs['initial_session']]+kwargs['observed_sessions'],'formal_dual_benchmark_admission':False}


class WrapperTests(unittest.TestCase):
    def test_exact40_slices_use_twr_not_account_equity_and_keep_rows(self):
        docs,refs=fixture(); compare=Mock(side_effect=mock_compare)
        result=module.assemble(docs,refs,compare)
        self.assertEqual(compare.call_count,40); self.assertEqual(result['comparison_role_count'],4)
        kwargs=compare.call_args_list[0].kwargs
        self.assertEqual(kwargs['candidate_cumulative_twr'][0]['cumulative_twr'],{'numerator':'0','denominator':'100'})
        self.assertNotIn('close_equity_usd',kwargs['candidate_cumulative_twr'][0])
        self.assertEqual(len(kwargs['incumbent_rows']),88)
        self.assertEqual(len(compare.call_args_list[-1].kwargs['incumbent_rows']),2)
        self.assertEqual(result['rows'][0]['input_row']['gaps'],['kept'])
        self.assertEqual(result['rows'][0]['observations']['candidate'][0]['source_row']['close_equity_usd'],'999999999')
        self.assertFalse(result['nav_dataset_currency_binding_certified'])
        self.assertTrue(result['annualized_return_calculated'])

    def test_missing_reference_duplicate_window_or_currency_upgrade_rejected(self):
        docs,refs=fixture(); docs['benchmark']['nav']['rows'].pop()
        with self.assertRaisesRegex(ValueError,'calendar'): module.assemble(docs,refs,mock_compare)
        docs,refs=fixture(); docs['accounts']['rows'][1]=deepcopy(docs['accounts']['rows'][0])
        with self.assertRaisesRegex(ValueError,'coordinate'): module.assemble(docs,refs,mock_compare)
        docs,refs=fixture(); docs['currency_manifest']['historical_2023_class_continuity_verified']=True
        with self.assertRaisesRegex(ValueError,'historical certification'): module.assemble(docs,refs,mock_compare)

    def test_publication_source_drift_and_existing_namespace_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); source=base/'source.py'; source.write_text('synthetic')
            parent=base/'parent'; parent.mkdir(); account=parent/'accounts.json'; account.write_bytes(module.encode({'source_hashes':{}}))
            (parent/'started.json').write_text('{}')
            receipt={'schema':'OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_PUBLICATION_V1','status':'PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS',
                'account_reference':{'path':str(account),'sha256':module.sha(account.read_bytes())},'source_hashes':{},
                'point_in_time_verified':False,'promotion_allowed':False,'orders_executed':False}
            pub=parent/'publication.json';pub.write_bytes(module.encode(receipt))
            pins={role:(str(path),module.sha(path.read_bytes())) for role,path in [('accounts',account),('publication',pub)]}
            output=base/'new'; original=module.write_new
            def drift(path,value):
                digest=original(path,value)
                if path.name=='publication.json': source.write_text('drift')
                return digest
            with patch.object(module,'SOURCE',source),patch.object(module,'LOADED_SHA',module.sha(source.read_bytes())),patch.object(module,'OUTPUT',output),patch.object(module,'PINS',pins),patch.object(module,'load_compare',return_value=Mock()),patch.object(module,'assemble',return_value={'synthetic':True}),patch.object(module,'write_new',side_effect=drift):
                with self.assertRaisesRegex(ValueError,'Source drift'): module.run()
                self.assertTrue((output/'failure.json').exists())
                with self.assertRaisesRegex(ValueError,'namespace exists'): module.run()


if __name__=='__main__': unittest.main()
