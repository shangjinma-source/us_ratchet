"""Independent offline AST accounting checks, without real API/account reads."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from backtest.parallel_deployment import build_parallel_deployment_plan


def endpoint_fixture(cash,price,gap,minimum_fee,ready=False):
    source=Path(__file__).resolve().parents[1]/'api/server.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='api_parallel_deployment')
    function.decorator_list=[]
    payload=dict(account_readiness=dict(position_gaps=dict(rows=[dict(ticker='AAA',gap_amount=gap,gap_ratio=1)] if gap else [])),symbols=[dict(ticker='AAA',price=price)],execution_constraints=dict(lot_size=1,min_fee=minimum_fee),broker_account=dict(available=True))
    env=dict(np=SimpleNamespace(isfinite=math.isfinite),load_portfolio=lambda path:object(),resolve=lambda path:path,STATE_PATH='OFFLINE_ONLY',_state_payload=lambda portfolio:payload,_parallel_deployment_readiness=lambda *args,**kwargs:dict(ready=ready,blockers=[] if ready else [dict(code='OFFLINE_STALE_ACCOUNT')]),build_parallel_deployment_plan=build_parallel_deployment_plan,CFG=SimpleNamespace(tactical_orders=SimpleNamespace(market_gate_enabled=True,bear_reserve_ratio=0)),JSONResponse=lambda content,status_code:SimpleNamespace(content=content,status_code=status_code))
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),env)
    return env['api_parallel_deployment'](cash_usd=cash)


class CashAccountingReview(unittest.TestCase):
    def test_full_input_and_blocked_scope_are_not_execution_permission(self):
        result=endpoint_fixture(20000,100,1000,5)
        pool=result['cash_pool']
        self.assertEqual(pool['input_pool_usd'],20000)
        self.assertEqual(pool['reserve_added_usd'],0)
        self.assertEqual(pool['allocated_notional_usd']+pool['estimated_fees_usd'],pool['draft_cash_used_usd'])
        self.assertEqual(pool['draft_cash_used_usd']+pool['cash_unallocated_usd'],pool['input_pool_usd'])
        self.assertFalse(pool['execution_authorized']); self.assertFalse(pool['dynamic_optimizer_admitted'])
        self.assertEqual(pool['capital_growth_status'],'REQUESTED_NOT_IMPLEMENTED')
        self.assertEqual(result['status'],'EXECUTION_READINESS_BLOCKED')

    def test_supported_fractional_cent_fee_components_conserve_display(self):
        # Each accepted input is in the existing endpoint/allocator domain.
        # Independent per-field display rounding must not invent an extra cent.
        pool=endpoint_fixture(1.01,.333,.999,.005)['cash_pool']
        self.assertAlmostEqual(pool['allocated_notional_usd']+pool['estimated_fees_usd'],pool['draft_cash_used_usd'],places=8)

    def test_unspent_subcent_input_is_not_erased(self):
        pool=endpoint_fixture(.004,100,0,0)['cash_pool']
        self.assertEqual(pool['draft_cash_used_usd'],0)
        self.assertEqual(pool['cash_unallocated_usd'],pool['input_pool_usd'])


if __name__=='__main__': unittest.main()
