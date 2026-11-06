"""Economic invariant: quote/cash refresh is not a fresh rebalance signal."""
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_store import StrategyAccountStore
from docs.candidates.frozen_target_builder_20261106 import FrozenTargetBuilder
from docs.candidates.frozen_target_provider_20261106 import digest


class FrozenQuantityRefreshTests(unittest.TestCase):
    def test_two_stock_cash_priority_reservation_and_partial_fill(self):
        with TemporaryDirectory() as directory:
            now=datetime.fromisoformat('2026-11-06T14:31:00+00:00')
            store=StrategyAccountStore(Path(directory)/'test.sqlite',clock=lambda:now)
            state=store.initialize('test',operation_id='init')
            def event(payload):
                nonlocal state
                state,_=store.append(payload,expected_revision=state['revision'])
            policy=dict(strategy_epoch='test',weights={'B':'1/10','A':'1/10'},
                target_quantities={'B':5,'A':5},signal_at='2026-11-05T21:00:00Z',
                valid_from='2026-11-06T14:30:00Z',valid_until='2026-11-06T21:00:00Z')
            quotes=dict(marks={s:dict(security_id=s,currency='USD',price_basis='current',price='100',observed_at=now.isoformat()) for s in ('A','B')},
                limits={s:dict(security_id=s,price_basis='current',buy='100',sell='100',observed_at=now.isoformat()) for s in ('A','B')})
            builder=FrozenTargetBuilder(directory=Path(directory)/'targets',policy=policy,
                contract_sha256=digest(policy),expected_epoch='test',account_id='test',
                store=store,quote_provider=lambda _:quotes,clock=lambda:now)
            def preview():
                version=builder.rebuild()
                return builder.preview(expected_revision=state['revision'],target_id=version['target_id'],expected_proposal_id=version['proposal_id'])['difference']
            event(dict(event_id='cash',kind='CASH_CONFIRM',amount='550',cash_basis='TOTAL_UNINVESTED'))
            result=preview()
            self.assertEqual([(o['security_id'],o['quantity']) for o in result['new_orders']],[('A',5)])
            self.assertEqual(result['unallocated_spendable_cash'],'50')
            self.assertEqual([(o['security_id'],o['quantity']) for o in result['waiting_cash']],[('B',5)])
            event(dict(event_id='partial',kind='DIRECT_FILL',security_id='A',side='BUY',quantity=2,price='100',fees='0',executed_at=now.isoformat()))
            event(dict(event_id='reserve',kind='ORDER_OPEN',order_id='buy-a',security_id='A',side='BUY',quantity=1,limit_price='100',fee_per_share='0'))
            event(dict(event_id='cash2',kind='CASH_CONFIRM',amount='350',cash_basis='TOTAL_UNINVESTED'))
            result=preview()
            # A has 2 filled + 1 pending: only 2 new shares. Reservation leaves
            # 250 spendable; the remaining 50 cannot fund any B share.
            self.assertEqual([(o['security_id'],o['quantity']) for o in result['new_orders']],[('A',2)])
            self.assertEqual(result['spendable_cash'],'250')
            self.assertEqual(result['unallocated_spendable_cash'],'50')
            self.assertEqual(result['binding']['buy_allocation_policy'],'SORTED_SECURITY_ID_SEQUENTIAL')
            self.assertEqual(store.read(),state)

    def test_defensive_target_requires_pending_buy_cancellation(self):
        # New-month defensive target must not reuse an old bullish proposal
        # or treat the broker's reserved cash as already released.
        with TemporaryDirectory() as directory:
            now = datetime.fromisoformat('2026-11-06T14:31:00+00:00')
            store = StrategyAccountStore(Path(directory)/'test.sqlite', clock=lambda:now)
            state = store.initialize('test', operation_id='init')
            def event(payload):
                nonlocal state
                state, _ = store.append(payload, expected_revision=state['revision'])
            event(dict(event_id='holding',kind='DIRECT_FILL',security_id='NEW',side='BUY',
                quantity=4,price='100',fees='0',executed_at=now.isoformat()))
            event(dict(event_id='pending',kind='ORDER_OPEN',order_id='pending-buy',security_id='NEW',
                side='BUY',quantity=3,limit_price='100',fee_per_share='0'))
            event(dict(event_id='cash',kind='CASH_CONFIRM',amount='700',cash_basis='AVAILABLE_AFTER_RESERVATIONS'))
            quotes = dict(marks={'NEW':dict(security_id='NEW',currency='USD',price_basis='current',
                price='100',observed_at=now.isoformat())},limits={'NEW':dict(security_id='NEW',
                price_basis='current',buy='100',sell='100',observed_at=now.isoformat())})
            policy = dict(strategy_epoch='defensive-test',weights={},target_quantities={},
                signal_at='2026-11-05T21:00:00Z',valid_from='2026-11-06T14:30:00Z',
                valid_until='2026-11-06T14:32:00Z')
            builder = FrozenTargetBuilder(directory=Path(directory)/'targets',policy=policy,
                contract_sha256=digest(policy),expected_epoch='defensive-test',account_id='test',
                store=store,quote_provider=lambda account:quotes,clock=lambda:now)
            def preview():
                version=builder.rebuild()
                return builder.preview(expected_revision=state['revision'],target_id=version['target_id'],
                    expected_proposal_id=version['proposal_id'])
            result=preview()
            self.assertEqual(result['target_quantities'],{})
            self.assertEqual(result['difference']['status'],'CANCEL_THEN_RECALCULATE')
            self.assertEqual(result['difference']['new_orders'],[])
            self.assertTrue(result['difference']['cancel_before_recalculate'])
            self.assertEqual(store.read(),state)
            with self.assertRaisesRegex(ValueError,'STALE_TARGET'):
                builder.preview(expected_revision=state['revision'],target_id='old-bullish',expected_proposal_id='old')

    def test_quotes_cash_and_partial_fill_preserve_target(self):
        with TemporaryDirectory() as directory:
            now = datetime.fromisoformat('2026-11-06T14:31:00+00:00')
            store = StrategyAccountStore(Path(directory)/'test.sqlite', clock=lambda: now)
            state = store.initialize('test', operation_id='init')
            policy = dict(strategy_epoch='test-frozen', weights={'NEW':'1'}, target_quantities={'NEW':10},
                signal_at='2026-11-05T21:00:00Z', valid_from='2026-11-06T14:30:00Z',
                valid_until='2026-11-06T14:32:00Z')
            quotes = dict(marks={'NEW':dict(security_id='NEW', currency='USD', price_basis='current',
                price='100', observed_at=now.isoformat())}, limits={'NEW':dict(security_id='NEW',
                price_basis='current', buy='100', sell='100', observed_at=now.isoformat())})
            builder = FrozenTargetBuilder(directory=Path(directory)/'targets', policy=policy,
                contract_sha256=digest(policy), expected_epoch='test-frozen', account_id='test',
                store=store, quote_provider=lambda account: quotes, clock=lambda:now)

            def preview():
                version = builder.rebuild()
                return builder.preview(expected_revision=store.read()['revision'],
                    target_id=version['target_id'], expected_proposal_id=version['proposal_id'])

            for index, (cash, price, affordable) in enumerate([
                    ('1000','100',10), ('1000','125',8), ('3000','125',10), ('500','125',4)]):
                state, _ = store.append(dict(event_id=f'cash-{index}', kind='CASH_CONFIRM',
                    amount=cash, cash_basis='TOTAL_UNINVESTED'), expected_revision=state['revision'])
                quotes['marks']['NEW']['price'] = price
                quotes['limits']['NEW'].update(buy=price, sell=price)
                result = preview()
                self.assertEqual(result['target_quantities'], {'NEW':10})
                self.assertEqual(result['difference']['new_orders'][0]['quantity'], affordable)
                self.assertEqual(store.read(), state)
            state, _ = store.append(dict(event_id='partial', kind='DIRECT_FILL', security_id='NEW',
                side='BUY', quantity=4, price='125', fees='0', executed_at=now.isoformat()),
                expected_revision=state['revision'])
            with self.assertRaisesRegex(ValueError, 'CASH_RECONFIRMATION_REQUIRED'):
                preview()
            state, _ = store.append(dict(event_id='after-fill', kind='CASH_CONFIRM', amount='1000',
                cash_basis='TOTAL_UNINVESTED'), expected_revision=state['revision'])
            result = preview()
            self.assertEqual(result['target_quantities'], {'NEW':10})
            self.assertEqual(result['difference']['new_orders'][0]['quantity'], 6)
            self.assertFalse(result['executable'])
            self.assertFalse(store.read()['orders'])


if __name__ == '__main__':
    unittest.main()
