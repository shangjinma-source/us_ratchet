"""Symbolic resource bounds against fictitious normal rows, never real points."""
from fractions import Fraction as F
import unittest
from backtest import ndx_double_replacement_resource_bounds_v2_research as bounds
from backtest import ndx_double_replacement_evaluation_research as oracle
from backtest import ndx_double_replacement_domain_research as domain


class Tests(unittest.TestCase):
    def test_complete_synthetic_rows_and_exact_digit_savings_across_fee_and_chain_shapes(self):
        for rate_bps, prices, retained, first in (
            ('0', ('2','3','0.7','1.1','1.3'), 0, 0),
            ('10', ('2.5','3','0.65','0.875','1.25'), 2, 95),
            ('175', ('2.25','3.125','0.9','0.6','1.125'), 3, 995),
        ):
            row=dict(execution_prices=dict(zip('abcde',prices)),holdings={'a':2,'b':3,'e':retained},securities={s:dict(risk_chain='shared' if s in 'cde' else s,issuer_id=s) for s in 'abcde'},target_weights={'a':'0.3','b':'0.7'},transaction_cost_bps=rate_bps,starting_cash_usd='4',cash_event={'amount_usd':'1'},minimum_cash_buffer_usd='0',risk_parameters=dict(max_single_weight='0.9',min_single_weight='0.01',top_weight_cap='1',minimum_effective_n_ratio='0.5',risk_chain_top1_cap='1'))
            rate=F(rate_bps)/10000;sale=F(prices[0])*2+F(prices[1])*3
            budget=F(5)+sale*(1-rate);costs=[F(p)*(1+rate) for p in prices[2:4]]
            qmax=[int((budget-costs[1-i])//costs[i]) for i in (0,1)]
            points=[(x,y) for x in range(1,qmax[0]+1) for y in range(1,qmax[1]+1) if costs[0]*x+costs[1]*y<=budget]
            pair=dict(financial_bound=dict(joint_budget_usd=str(budget),incoming_unit_costs_with_buy_fee_usd=list(map(str,costs))),outgoing_security_ids=['a','b'],incoming_security_ids=['c','d'],sell_quantities={'a':2,'b':3},pair_index=0,enumerable_integer_count=len(points),first_global_ordinal=first)
            case=dict(identity={'original_input_row':row},identity_sha256='a'*64,scenario_index=0)
            result=bounds.pair_bound(case,pair,rule=domain.RULE,flags=domain.FLAGS,checks=oracle.CHECKS,full_count=first+len(points))
            saved=actual_bytes=0;last=first+len(points)-1
            for i,(x,y) in enumerate(points):
                identity=dict(schema='DOUBLE_REPLACEMENT_INTEGER_TASK_IDENTITY_V1',scenario_identity_sha256=case['identity_sha256'],rule=domain.RULE,outgoing_security_ids=['a','b'],incoming_security_ids=['c','d'],sell_quantities={'a':2,'b':3},buy_quantities=[x,y])
                task=dict(task_id='f'*64,identity=identity,scenario_index=0,pair_index=0,global_ordinal=first+i,signed_trade_quantities={'a':-2,'b':-3,'c':x,'d':y,'e':0},proposed_holdings={'a':0,'b':0,'c':x,'d':y,'e':retained},evaluation_status='NOT_EVALUATED',**domain.FLAGS)
                evaluation=oracle.evaluate_one(row,task)
                normal=dict(supplied_index=i%10000,plan=dict(global_ordinal=first+i,task=task),status=evaluation['status'],evaluation=evaluation)
                saving=3*sum(len(str(maximum))-len(str(q)) for maximum,q in zip(qmax,(x,y)))+2*(len(str(last))-len(str(first+i)))
                self.assertLessEqual(len(bounds.encode(normal)),result['row_bytes']-saving)
                self.assertEqual(evaluation['financial_checks'],dict(NONNEGATIVE_CASH=True,CASH_BUFFER=True))
                for field,limit in result['field_char_bounds'].items():self.assertLessEqual(len(evaluation[field]),limit,field)
                self.assertLessEqual(len(evaluation['risk']['effective_n']),result['effective_chars'])
                for sid,value in evaluation['risk']['weights'].items():self.assertLessEqual(len(value),result['weight_char_bounds'][sid])
                for chain,value in evaluation['risk']['risk_chain_weights'].items():self.assertLessEqual(len(value),result['chain_char_bounds'][chain])
                saved+=saving;actual_bytes+=len(bounds.encode(normal))
            self.assertEqual(saved,result['integer_digit_savings'])
            self.assertLessEqual(actual_bytes,result['count']*result['row_bytes']-saved)

    def test_aggregated_zlib_expansion_dominates_sum_of_per_stream_bounds(self):
        for sizes in ((0,), (1,4095,4096,16383,16384), (33554431,33554432,33554433)):
            total=sum(sizes)
            summed=sum(bounds.gzip_default_zlib_bound(n) for n in sizes)
            aggregate=total+(total>>12)+(total>>14)+(total>>25)+31*len(sizes)
            self.assertGreaterEqual(aggregate,summed)


if __name__=='__main__':unittest.main()
