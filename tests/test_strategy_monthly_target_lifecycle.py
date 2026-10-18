"""Lifecycle tests with real temporary journals and difference calculations.
The injected selector counts calls; no economic experiment or live data runs.
"""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_monthly_target_service import StrategyMonthlyTargetService,LIFECYCLE_PATHS

class Selection:
    def __init__(self,store):
        self.store=store;self.pins={path:'a'*64 for path in LIFECYCLE_PATHS};self.age=120;self.fees='0';self.calls=0;self.quantity=14;self.fail=False
    def _pins(self):pass
    def generate(self):
        self.calls+=1
        if self.fail:return {'status':'BLOCKED','reason':'SOURCE_UNAVAILABLE'}
        state=self.store.read();payload={'target_quantities':{'A':self.quantity} if self.quantity else {}}
        decision={'payload':payload,'decision_id':sha256(canonical(payload)).hexdigest()}
        self.current=(decision,{},state);return {'status':'READY'}

class MonthlyLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.now=datetime(2026,10,16,15,tzinfo=timezone.utc);self.sequence=0
        self.account=StrategyAccountStore(self.root/'account.db',clock=lambda:self.now)
        self.account.initialize('s',operation_id='init');self.event('CASH_CONFIRM',amount='2000',cash_basis='TOTAL_UNINVESTED')
        self.targets=StrategyMonthlyTargetStore(self.root/'targets.db');self.selection=Selection(self.account)
        self.evidence_age=0;self.service=self.make()
    def make(self):
        return StrategyMonthlyTargetService(selection_service=self.selection,target_store=self.targets,execution_provider=self.evidence,clock=lambda:self.now)
    def event(self,kind,**fields):
        self.sequence+=1;state=self.account.read()
        return self.account.append(dict(event_id=str(self.sequence),kind=kind,**fields),expected_revision=state['revision'])
    def evidence(self,state,target,now):
        at=(now-timedelta(seconds=self.evidence_age)).isoformat()
        ids=set(target['payload']['target_quantities'])|{sid for sid,q in state['shares'].items() if q}|{o['security_id'] for o in state['orders'].values() if o['status']=='OPEN'}
        return dict(marks={sid:dict(security_id=sid,currency='USD',price_basis='CURRENT_UNIT',observed_at=at,price='100') for sid in ids},
            limits={sid:dict(security_id=sid,ticker='TEST-'+sid,price_basis='CURRENT_UNIT',observed_at=at,buy='100',sell='100',buy_reason='回落价，允许不成交',sell_reason='近现价减仓参考',reference_valid_until=(now+timedelta(seconds=90)).isoformat()) for sid in ids})
    def generate(self,event_id='target1',reason='INITIAL'):
        prior=self.targets.current()
        return self.service.generate(event_id=event_id,reason=reason,expected_revision=self.account.read()['revision'],previous_target_id=prior['target_id'] if prior else None)
    def test_daily_refresh_fill_cash_pending_and_restart(self):
        target=self.generate();self.assertEqual(self.selection.calls,1)
        for _ in range(3):self.assertEqual(self.service.preview()['difference']['new_orders'][0]['quantity'],14)
        self.event('ORDER_OPEN',order_id='real-order',security_id='A',side='BUY',quantity=14,limit_price='100',fee_per_share='0')
        self.event('FILL',order_id='real-order',quantity=5,price='100',fees='0',executed_at=self.now.isoformat())
        with self.assertRaisesRegex(ValueError,'CASH_RECONFIRMATION_REQUIRED'):self.service.preview()
        self.event('CASH_CONFIRM',amount='1500',cash_basis='TOTAL_UNINVESTED')
        self.assertEqual(self.account.read()['orders']['real-order']['remaining_quantity'],9)
        preview=self.service.preview();self.assertEqual(preview['difference']['new_orders'],[])
        self.assertEqual(self.selection.calls,1)
        self.event('CANCEL',order_id='real-order')
        self.assertEqual(self.service.preview()['difference']['new_orders'][0]['quantity'],9)
        self.event('CASH_CONFIRM',amount='1300',cash_basis='TOTAL_UNINVESTED')
        self.assertEqual(self.service.preview()['target_id'],target['target_id']);self.assertEqual(self.selection.calls,1)
        self.service=self.make();self.assertEqual(self.service.current(),target)
        self.assertEqual(self.service.preview()['difference']['new_orders'][0]['quantity'],9)
    def test_expiry_month_failure_and_explicit_replacement(self):
        target=self.generate();self.selection.age=900;self.evidence_age=121
        with self.assertRaises(ValueError):self.service.preview()
        self.assertEqual(self.service.current(),target);self.evidence_age=0
        self.assertEqual(self.service.preview()['target_id'],target['target_id'])
        self.selection.fail=True
        with self.assertRaisesRegex(ValueError,'SOURCE_UNAVAILABLE'):self.generate('failed','EXPLICIT_RECONFIGURE')
        self.assertEqual(self.service.current(),target);self.selection.fail=False
        self.now=datetime(2026,11,2,15,tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError,'MONTHLY_TARGET_REQUIRED'):self.service.preview()
        self.assertEqual(self.service.current(),target)
        new=self.generate('nov','MONTHLY_SELECTION');self.assertEqual(new['payload']['previous_target_id'],target['target_id'])
        self.assertEqual(new['payload']['target_month'],'2026-11')
    def test_idempotent_generation_cas_and_pending_conflict(self):
        before=self.account.read()['revision'];target=self.generate()
        self.event('CASH_CONFIRM',amount='1900',cash_basis='TOTAL_UNINVESTED')
        self.assertEqual(self.service.generate(event_id='target1',reason='INITIAL',expected_revision=before,previous_target_id=None),target)
        self.assertEqual(self.selection.calls,1)
        with self.assertRaisesRegex(ValueError,'STALE_TARGET'):
            self.service.generate(event_id='wrong',reason='EXPLICIT_RECONFIGURE',expected_revision=self.account.read()['revision'],previous_target_id='bad')
        self.event('ORDER_OPEN',order_id='buy',security_id='A',side='BUY',quantity=14,limit_price='100',fee_per_share='0')
        self.event('CASH_CONFIRM',amount='1900',cash_basis='TOTAL_UNINVESTED');self.selection.quantity=5
        new=self.generate('smaller','EXPLICIT_RECONFIGURE')
        self.assertEqual(self.service.preview()['difference']['status'],'CANCEL_THEN_RECALCULATE')
        self.assertEqual(new['payload']['request']['reason'],'EXPLICIT_RECONFIGURE')
    def test_read_missing_no_create(self):
        empty=StrategyMonthlyTargetStore(self.root/'absent'/'targets.db')
        self.assertIsNone(empty.current());self.assertFalse(empty.path.parent.exists())
    def test_order_display_fields_buy_reduce_exit_and_empty_result(self):
        self.generate();preview=self.service.preview();order=preview['difference']['new_orders'][0]
        self.assertEqual(order['ticker'],'TEST-A')
        self.assertEqual(order['execution_reason'],'回落价，允许不成交')
        self.assertEqual(order['strategy_reason'],'补足本月目标持仓')
        self.assertEqual(order['observed_at'],self.now.isoformat())
        self.assertEqual(order['reference_valid_until'],preview['reference_valid_until'])
        self.assertEqual(preview['generated_at'],self.now.isoformat())
        self.event('DIRECT_FILL',security_id='A',side='BUY',quantity=5,price='100',fees='0',executed_at=self.now.isoformat())
        self.event('CASH_CONFIRM',amount='1500',cash_basis='TOTAL_UNINVESTED')
        self.selection.quantity=2;self.generate('reduce','EXPLICIT_RECONFIGURE')
        order=self.service.preview()['difference']['new_orders'][0]
        self.assertEqual((order['side'],order['quantity']),('SELL',3))
        self.assertEqual(order['execution_reason'],'近现价减仓参考')
        self.assertEqual(order['strategy_reason'],'当前持仓高于本月目标，减仓至目标')
        self.selection.quantity=0;self.generate('exit','EXPLICIT_RECONFIGURE')
        self.assertEqual(self.service.preview()['difference']['new_orders'][0]['strategy_reason'],'本月目标为零，退出持仓')
        self.event('DIRECT_FILL',security_id='A',side='SELL',quantity=5,price='100',fees='0',executed_at=self.now.isoformat())
        self.event('CASH_CONFIRM',amount='2000',cash_basis='TOTAL_UNINVESTED')
        self.assertIsNone(self.service.preview()['reference_valid_until'])
    def test_real_tiny_selector_once_then_daily_difference_without_search(self):
        from unittest.mock import patch
        from test_strategy_account_target_service import ServiceTests
        from data import strategy_account_target_decision as decision_module
        selection,clock,_,account=ServiceTests().fixture(self.temp.name)
        for name in LIFECYCLE_PATHS:
            raw=(Path(__file__).resolve().parents[1]/name).read_bytes()
            destination=selection.root/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
            selection.pins[name]=sha256(raw).hexdigest()
        target_store=StrategyMonthlyTargetStore(self.root/'real-target.db')
        def evidence(state,target,now):
            limits=deepcopy(selection.current[1])
            for limit in limits.values():limit['reference_valid_until']=(now+timedelta(seconds=90)).isoformat()
            return dict(marks=deepcopy(selection.current[0]['payload']['input_binding']['marks']),limits=limits)
        service=StrategyMonthlyTargetService(selection_service=selection,target_store=target_store,execution_provider=evidence,clock=lambda:clock[0])
        with patch.object(decision_module,'search_fresh_cash_quantities',wraps=decision_module.search_fresh_cash_quantities) as search:
            target=service.generate(event_id='real',reason='INITIAL',expected_revision=account.read()['revision'],previous_target_id=None)
            for _ in range(3):self.assertEqual(service.preview()['target_id'],target['target_id'])
            self.assertEqual(search.call_count,1)
    def test_final_deadline_missing_and_expired_rejected_without_losing_target(self):
        target=self.generate();original=self.service.execution_provider
        for mode in ('missing','expired','crossed_during_final_checks'):
            with self.subTest(mode=mode):
                def evidence(state,target,now):
                    data=original(state,target,now)
                    for limit in data['limits'].values():
                        if mode=='missing':del limit['reference_valid_until']
                        else:limit['reference_valid_until']=(now+timedelta(seconds=1 if mode=='crossed_during_final_checks' else 0)).isoformat()
                    if mode=='crossed_during_final_checks':self.now+=timedelta(seconds=1)
                    return data
                self.service.execution_provider=evidence
                with self.assertRaisesRegex(ValueError,'EXECUTION_DEADLINE_REQUIRED|REQUOTE_REQUIRED'):self.service.preview()
                self.assertEqual(self.service.current(),target)
                self.assertEqual(self.selection.calls,1)

if __name__=='__main__':unittest.main()
