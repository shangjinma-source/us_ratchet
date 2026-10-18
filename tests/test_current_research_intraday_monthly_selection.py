import tempfile
import unittest
from copy import deepcopy
from datetime import datetime,timedelta
from unittest.mock import patch
import test_current_research_monthly_retarget_capital as fixtures
from data.current_research_monthly_retarget_capital import build_monthly_retarget_capital
from data.current_research_intraday_monthly_selection import build_intraday_monthly_top1_selection

class BridgeTests(unittest.TestCase):
    def fixture(self,root):
        state,capargs=fixtures.CapitalTests().fixture(root)
        now=datetime.fromisoformat('2026-11-02T12:00:00-05:00')
        capargs['now']=now
        capargs['market_session'].update(date='2026-11-02',open_at='2026-11-02T09:30:00-05:00',close_at='2026-11-02T16:00:00-05:00')
        capargs['valuation_quotes'][0].update(quoted_at=now.isoformat(),captured_at=now.isoformat())
        capargs['unit_continuity']['sndk'].update(covered_through=now.isoformat(),reviewed_asof=now.isoformat())
        capital=build_monthly_retarget_capital(state,**capargs)
        dates=[];day=datetime(2026,10,30)
        while len(dates)<253:
            if day.weekday()<5:dates.append(day.date().isoformat())
            day-=timedelta(days=1)
        dates.reverse();pins=dict(capargs['source_hashes'],training='d'*64)
        pins['backtest/return_priority_monthly_top1_selector.py']='e'*64
        args=dict(prices={'new':'50','other':'100'},metadata={'new':{'ticker':'NEW','issuer_id':'newissuer'},'other':{'ticker':'OTHER','issuer_id':'otherissuer'}},training_scenarios=[{'new':'11/10','other':'1'} for _ in range(12)],scenario_dates=dates[21::21],decision_date=dates[-1],entered_cash='20000',fee_bps='0',minimum_cash_buffer='0')
        training=dict(search_arguments=args,training_dates=dates,scenario_start_dates=dates[0:252:21],eligible_security_ids=['new','other'],universe_security_ids=['new','other','excluded'],exclusions={'excluded':'explicit synthetic short history'},admission_status='REVIEWED_CONDITIONAL_COMPLETE_DOMAIN',training_coordinate_policy='SYNTHETIC_FIXED_COORDINATE',decision_price_date=dates[-1],decision_price_basis='SYNTHETIC_DECISION_NOMINAL',source_references=['training'],source_hashes={'training':'d'*64},decision_session_close_at='2026-10-30T16:00:00-04:00')
        capargs.pop('now')
        return state,dict(capital=capital,capital_inputs=capargs,training_input=training,target_month='2026-11',selection_calendar=['2026-10-30','2026-11-02'],source_hashes=pins,now=now)
    def test_equity_not_original_budget_and_not_execution_quantity(self):
        with tempfile.TemporaryDirectory() as root:
            state,args=self.fixture(root);before=deepcopy(state)
            result=build_intraday_monthly_top1_selection(state,**args)
            self.assertEqual(result['status'],'READY',result)
            self.assertEqual(result['historical_reference_target_quantities'],{'new':404})
            self.assertEqual(result['investable_equity'],'20200');self.assertEqual(result['buy_cash_limit'],'17200')
            self.assertNotIn('target_quantities',result);self.assertEqual(result['selector_calls'],1);self.assertEqual(result['core_calls'],0)
            self.assertEqual(state,before);self.assertFalse(result['global_optimum_established'])
    def test_invalid_capital_and_domain_reject_before_selection(self):
        with tempfile.TemporaryDirectory() as root:
            state,args=self.fixture(root)
            for mode in ('capital','coverage','maturity','month'):
                a=deepcopy(args)
                if mode=='capital':a['capital']['capital']['investable_equity']='30000'
                if mode=='coverage':a['training_input']['universe_security_ids'].append('missing')
                if mode=='maturity':a['training_input']['search_arguments']['scenario_dates'][-1]='2026-11-03'
                if mode=='month':a['target_month']='2026-12'
                with patch('data.current_research_intraday_monthly_selection.select_top1_quantities',side_effect=AssertionError('must not call')):
                    self.assertEqual(build_intraday_monthly_top1_selection(state,**a)['status'],'BLOCKED')
    def test_no_old_holdings_filter_and_decision_id_binds_sources(self):
        with tempfile.TemporaryDirectory() as root:
            state,args=self.fixture(root)
            result=build_intraday_monthly_top1_selection(state,**args)
            self.assertEqual(result['selected_security_id'],'new')
            args['source_hashes']['training']='f'*64;args['training_input']['source_hashes']['training']='f'*64
            other=build_intraday_monthly_top1_selection(state,**args)
            self.assertNotEqual(result['decision_id'],other['decision_id'])

if __name__=='__main__':unittest.main()
