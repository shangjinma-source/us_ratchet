import unittest
from copy import deepcopy
from fractions import Fraction
from unittest.mock import patch
from backtest.two_stage_execution_research_v1 import TwoStageExecution, uncapped_winner


def fixture(held=0, target=5, side='BUY', epoch='2023-01-31'):
    return dict(status='READY', target_decision_date=epoch, target_shares={'S': target},
                monthly_ceiling={'S': target}, risk_overlay={'unchanged': True},
                orders=[dict(id='original', security_id='S', side=side,
                             quantity=abs(target-held), decision_date='2023-01-31',
                             active_date='2023-02-01', decision_mark='10')])


def account(held=0, logs=()):
    return dict(shares={'S': held}, cash='100', order_log=list(logs))


def adjust(stage, result, state, day='2023-01-31', active='2023-02-01'):
    return stage.adjust(result, state=state, decision_date=day, active_date=active)


class StagingTests(unittest.TestCase):
    def test_real_kernel_baseline_exact_and_buy_fill_advances(self):
        from test_capped_frontier_independent_review import inputs, raw_fixture
        from backtest import historical_dividend_frontier_research as frontier
        from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
        from backtest.two_stage_execution_research_v1 import run_staged
        domain,bars=inputs()
        def arguments():
            return dict(assembled=deepcopy(domain),ohlc=deepcopy(bars),initial_cash='20000',
                        fee_bps='1',slippage_bps='10',max_new_searches=1,
                        risk=MonthlyExitCoreResearchAdapter([]))
        with patch.object(frontier,'decide_continuous_guided_for_account',side_effect=lambda **args: raw_fixture(args)):
            original=frontier.run_frontier_capped_next_open(**arguments())
        baseline=run_staged(mode='BASELINE',selector=lambda **args: raw_fixture(args),**arguments())
        for key,value in original.items():
            self.assertEqual(baseline[key],value,key)
        staged=run_staged(mode='BUY_TWO_OPENS',selector=lambda **args: raw_fixture(args),**arguments())
        self.assertEqual(staged['status'],'COMPLETE',staged.get('reason'))
        fills=[r for r in staged['order_log'] if r.get('event')=='ASSUMED_NEXT_OPEN_FILLED' and r['side']=='BUY']
        self.assertEqual([r['quantity'] for r in fills[:2]],[49,49])
        self.assertEqual([r['quantity'] for r in fills[2:4]],[50,50])
        self.assertTrue(all(r['id'].startswith('stage:') for r in fills))
        self.assertEqual(staged['execution_stage_audit'][1]['decisions'][0]['phase'],2)
        self.assertTrue(all(Fraction(r['cash'])>=0 for r in staged['daily_ledger']))
        sell=[r for r in staged['order_log'] if r.get('event')=='ASSUMED_NEXT_OPEN_FILLED' and r['side']=='SELL']
        self.assertTrue(any(r['security_id']=='A' and r['quantity']==99 for r in sell))

    def test_failed_exposure_callback_restores_hooks(self):
        from test_capped_frontier_independent_review import inputs,raw_fixture
        from backtest import historical_dividend_frontier_research as frontier
        from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
        from backtest.two_stage_execution_research_v1 import run_staged
        domain,bars=inputs()
        before=(frontier.decide_continuous_guided_for_account,frontier.rerank,frontier.run_next_open_book)
        def fail(*args):raise ValueError('FIXTURE_EXPOSURE_BLOCK')
        result=run_staged(mode='BUY_TWO_OPENS',assembled=domain,ohlc=bars,initial_cash='20000',fee_bps='1',slippage_bps='10',max_new_searches=1,risk=MonthlyExitCoreResearchAdapter([]),selector=lambda **args: raw_fixture(args),decision_callback=fail)
        self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(before,(frontier.decide_continuous_guided_for_account,frontier.rerank,frontier.run_next_open_book))

    def test_unfilled_cap_stage_never_delays_new_noncap_quantity(self):
        s=TwoStageExecution('CAP_SELL_TWO_OPENS');s.winners['2023-01-31']={'quantities':{'S':8},'capped':{'S':4}}
        self.assertEqual(adjust(s,fixture(8,4,'SELL'),account(8))['orders'][0]['quantity'],2)
        self.assertEqual(adjust(s,fixture(13,4,'SELL'),account(13),'2023-02-01','2023-02-02')['orders'][0]['quantity'],5)

    def test_buy_partial_fill_advances_and_no_fill_keeps_anchor(self):
        s=TwoStageExecution('BUY_TWO_OPENS');r=fixture()
        first=adjust(s,r,account());self.assertEqual(first['orders'][0]['quantity'],2)
        nofill=adjust(s,r,account(), '2023-02-01','2023-02-02')
        self.assertEqual(nofill['orders'][0]['quantity'],2)
        fill=dict(event='ASSUMED_NEXT_OPEN_FILLED',id=first['orders'][0]['id'],quantity=1)
        second=adjust(s,fixture(1,5),account(1,[fill]),'2023-02-02','2023-02-03')
        self.assertEqual(second['orders'][0]['quantity'],4)
        self.assertEqual(second['target_shares'],r['target_shares'])
        self.assertEqual(second['risk_overlay'],r['risk_overlay'])

    def test_one_share_skip_then_complete(self):
        s=TwoStageExecution('BUY_TWO_OPENS')
        self.assertEqual(adjust(s,fixture(0,1),account())['orders'],[])
        self.assertEqual(adjust(s,fixture(0,1),account(),'2023-02-01','2023-02-02')['orders'][0]['quantity'],1)

    def test_risk_exit_priority_and_new_epoch(self):
        s=TwoStageExecution('BUY_TWO_OPENS');adjust(s,fixture(),account())
        exit_result=fixture(3,0,'SELL');exit_result['monthly_ceiling']={'S':5}
        self.assertEqual(adjust(s,exit_result,account(3),'2023-02-01','2023-02-02')['orders'][0]['quantity'],3)
        self.assertEqual(s.episodes,{})
        self.assertEqual(adjust(s,fixture(0,8,epoch='2023-02-28'),account(),'2023-02-28','2023-03-01')['orders'][0]['quantity'],4)

    def test_cap_sale_separates_noncap_and_second_actual_gap(self):
        s=TwoStageExecution('CAP_SELL_TWO_OPENS');s.winners['2023-01-31']={'quantities':{'S':8},'capped':{'S':4}}
        first=adjust(s,fixture(10,4,'SELL'),account(10))
        self.assertEqual(first['orders'][0]['quantity'],4)  # 2 noncap + 2 cap
        fill=dict(event='ASSUMED_NEXT_OPEN_FILLED',id=first['orders'][0]['id'],quantity=3)
        second=adjust(s,fixture(7,4,'SELL'),account(7,[fill]),'2023-02-01','2023-02-02')
        self.assertEqual(second['orders'][0]['quantity'],3)
        exit_result=fixture(7,0,'SELL');exit_result['monthly_ceiling']={'S':4}
        self.assertEqual(adjust(s,exit_result,account(7),'2023-02-02','2023-02-03')['orders'][0]['quantity'],7)

    def test_plain_reselection_sell_not_cap(self):
        s=TwoStageExecution('CAP_SELL_TWO_OPENS');s.winners['2023-01-31']={'quantities':{'S':4},'capped':{'S':4}}
        self.assertEqual(adjust(s,fixture(10,4,'SELL'),account(10))['orders'][0]['quantity'],6)

    def test_pending_company_action_rejected(self):
        s=TwoStageExecution('BUY_TWO_OPENS');adjust(s,fixture(),account())
        r=fixture();r['target_adjustments']=[{'security_id':'S'}]
        with self.assertRaisesRegex(ValueError,'COORDINATE_REVIEW'):
            adjust(s,r,account(),'2023-02-01','2023-02-02')

    def test_uncapped_provenance_strict_vs_incumbent(self):
        raw={'binding':{'search_arguments':{'entered_cash':'100','prices':{'S':'10'}}},
             'investable_equity':'100','target_quantities':{'S':9},
             'search_result':{'best_by_k':{'1':{'quantities':{'S':7}}}}}
        selected={'raw_selection':raw,'rerank_audit':{'strict_improvement':False,'source_cardinality':1},'target_quantities':{'S':5}}
        self.assertEqual(uncapped_winner(selected)['quantities'],{'S':9})
        selected['rerank_audit']['strict_improvement']=True
        self.assertEqual(uncapped_winner(selected)['quantities'],{'S':7})
        selected['target_quantities']['S']=4
        with self.assertRaisesRegex(ValueError,'WINNER_BINDING'):
            uncapped_winner(selected)


if __name__=='__main__':unittest.main()

