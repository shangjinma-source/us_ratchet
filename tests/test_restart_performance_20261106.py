import unittest
from core.strategy_account_ledger import create_account, apply_event
from data.strategy_restart_performance import restart_performance

class PerformanceTests(unittest.TestCase):
    def test_reserved_cash_is_not_external_flow(self):
        state=create_account('reserved-fixture')
        def event(state,**payload):
            return apply_event(state,payload,expected_revision=state['revision'])[0]
        state=event(state,event_id='initial',kind='CASH_CONFIRM',amount='1000',cash_basis='AVAILABLE_AFTER_RESERVATIONS')
        baseline=dict(initial_equity='1000',cash='1000',effective_at='2026-11-06T14:30:00Z',account_revision=state['revision'],holdings=[])
        current=event(state,event_id='open',kind='ORDER_OPEN',order_id='order',security_id='X',side='BUY',quantity=2,limit_price='100',fee_per_share='1')
        current=event(current,event_id='confirm',kind='CASH_CONFIRM',amount='798',cash_basis='AVAILABLE_AFTER_RESERVATIONS')
        value=dict(status='READY',cash_confirmed=True,account_revision=current['revision'],valued_at='2026-11-06T14:32:00Z',market_value='0',strategy_total='1000',holdings=[])
        result=restart_performance(baseline=baseline,valuations=[value],account_evidence={current['revision']:dict(baseline_account=state,current_account=current)})
        self.assertEqual(result['return_fraction'],'0')
    def test_trade_reconciliation_and_unknown_cash(self):
        state=create_account('fixture')
        def event(state,**payload):
            return apply_event(state,payload,expected_revision=state['revision'])[0]
        state=event(state,event_id='cash0',kind='CASH_CONFIRM',amount='1000',cash_basis='AVAILABLE_AFTER_RESERVATIONS')
        baseline=dict(initial_equity='1000',cash='1000',effective_at='2026-11-06T14:30:00Z',account_revision=state['revision'],holdings=[])
        traded=event(state,event_id='buy',kind='DIRECT_FILL',security_id='X',side='BUY',quantity=2,price='100',fees='1',executed_at='2026-11-06T14:31:00Z')
        traded=event(traded,event_id='cash1',kind='CASH_CONFIRM',amount='799',cash_basis='AVAILABLE_AFTER_RESERVATIONS')
        value=dict(status='READY',cash_confirmed=True,account_revision=traded['revision'],valued_at='2026-11-06T14:32:00Z',market_value='220',strategy_total='1019',holdings=[dict(security_id='X',quantity=2,price='110',market_value='220',observed_at='2026-11-06T14:32:00Z')])
        evidence={traded['revision']:dict(baseline_account=state,current_account=traded)}
        result=restart_performance(baseline=baseline,valuations=[value],account_evidence=evidence)
        self.assertEqual(result['return_fraction'],'19/1000')
        self.assertIsNone(result['maximum_drawdown_fraction'])
        changed=event(traded,event_id='unknown',kind='CASH_CONFIRM',amount='899',cash_basis='AVAILABLE_AFTER_RESERVATIONS')
        bad=dict(value,account_revision=changed['revision'],strategy_total='1119')
        result=restart_performance(baseline=baseline,valuations=[bad],account_evidence={changed['revision']:dict(baseline_account=state,current_account=changed)})
        self.assertEqual(result['reason'],'UNCLASSIFIED_CASH_CHANGE')
        lower=dict(value,valued_at='2026-11-06T14:33:00Z',market_value='180',strategy_total='979',holdings=[dict(security_id='X',quantity=2,price='90',market_value='180',observed_at='2026-11-06T14:33:00Z')])
        result=restart_performance(baseline=baseline,valuations=[value,lower],account_evidence=evidence,expected_sample_times=[value['valued_at'],lower['valued_at']])
        self.assertEqual(result['maximum_drawdown_fraction'],'40/1019')
        self.assertEqual(result['drawdown_scope'],'DECLARED_SAMPLES_ONLY')
        rolled_back=dict(status='READY',cash_confirmed=True,account_revision=state['revision'],valued_at='2026-11-06T14:34:00Z',market_value='0',strategy_total='1000',holdings=[])
        result=restart_performance(baseline=baseline,valuations=[value,rolled_back],account_evidence=evidence)
        self.assertEqual(result['reason'],'ACCOUNT_HISTORY_REGRESSION')
        alternate=event(state,event_id='alternative',kind='CASH_CONFIRM',amount='1000',cash_basis='AVAILABLE_AFTER_RESERVATIONS')
        forked=dict(rolled_back,account_revision=alternate['revision'])
        result=restart_performance(baseline=baseline,valuations=[value,forked],account_evidence=dict(evidence,**{alternate['revision']:dict(baseline_account=state,current_account=alternate)}))
        self.assertEqual(result['reason'],'ACCOUNT_HISTORY_REGRESSION')
if __name__=='__main__':unittest.main()
