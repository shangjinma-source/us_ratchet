import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import datetime
from core.strategy_account_store import StrategyAccountStore
from docs.candidates.target_account_bridge_20261106 import preview_target_weights

class BridgeTests(unittest.TestCase):
    def test_cash_increase_decrease_rebuilds_targets_from_real_ledger(self):
        # Synthetic funds and generic legacy security: no private snapshot fixture.
        with TemporaryDirectory() as folder:
            now = datetime.fromisoformat('2026-11-06T14:31:00+00:00')
            store = StrategyAccountStore(Path(folder)/'account.sqlite3', clock=lambda: now)
            state = store.initialize('isolated-cash-transition', operation_id='init')
            state, _ = store.append(dict(event_id='legacy', kind='DIRECT_FILL', security_id='LEGACY', side='BUY', quantity=14, price='100', fees='0', executed_at='2026-11-05T15:00:00Z'), expected_revision=state['revision'])
            marks = {sid:dict(security_id=sid,currency='USD',price_basis='current',observed_at=now.isoformat(),price='100') for sid in ['LEGACY','NEW']}
            limits = {sid:dict(security_id=sid,price_basis='current',observed_at=now.isoformat(),buy='100',sell='100') for sid in marks}
            revisions = []
            for index, (cash, target, affordable) in enumerate([('1000',24,10),('3000',44,30),('500',19,5)]):
                state, _ = store.append(dict(event_id=f'cash-{index}',kind='CASH_CONFIRM',amount=cash,cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=state['revision'])
                revisions.append(state['revision'])
                result = preview_target_weights(account=state, expected_revision=state['revision'], weights={'NEW':'1'}, marks=marks, limits=limits, signal_at='2026-11-05T21:00:00Z', valid_from='2026-11-06T14:30:00Z', valid_until='2026-11-06T14:32:00Z', now=now.isoformat(), contract_hash='b'*64)
                self.assertEqual(result['target_quantities'], {'NEW':target})
                orders = {(o['security_id'],o['side']):o['quantity'] for o in result['difference']['new_orders']}
                self.assertEqual(orders, {('LEGACY','SELL'):14,('NEW','BUY'):affordable})
                self.assertEqual(store.read(), state)
                self.assertEqual(state['shares']['LEGACY'],14)
                self.assertFalse(state['orders'])
                self.assertFalse(result['production_activated'])
            self.assertEqual(len(set(revisions)),3)

    def test_existing_position_cash_bound_no_assumed_sale_proceeds(self):
        with TemporaryDirectory() as folder:
            now = datetime.fromisoformat('2026-11-06T14:31:00+00:00')
            store = StrategyAccountStore(Path(folder)/'account.sqlite3', clock=lambda: now)
            state = store.initialize('test', operation_id='init')
            state, _ = store.append(dict(event_id='old', kind='DIRECT_FILL', security_id='OLD', side='BUY', quantity=3, price='100', fees='0', executed_at='2026-11-05T15:00:00Z'), expected_revision=state['revision'])
            state, _ = store.append(dict(event_id='cash', kind='CASH_CONFIRM', amount='1250.00', cash_basis='AVAILABLE_AFTER_RESERVATIONS'), expected_revision=state['revision'])
            marks = {sid:dict(security_id=sid,currency='USD',price_basis='current',observed_at=now.isoformat(),price='100') for sid in ['OLD','NEW']}
            limits = {sid:dict(security_id=sid,price_basis='current',observed_at=now.isoformat(),buy='100',sell='100') for sid in marks}
            args = dict(account=state,expected_revision=state['revision'],marks=marks,limits=limits,signal_at='2026-11-05T21:00:00Z',valid_from='2026-11-06T14:30:00Z',valid_until='2026-11-06T14:32:00Z',now=now.isoformat(),contract_hash='a'*64)
            result = preview_target_weights(weights={'NEW':'1'},**args)
            self.assertEqual(result['target_quantities'],{'NEW':15})
            orders = {(o['security_id'],o['side']):o['quantity'] for o in result['difference']['new_orders']}
            self.assertEqual(orders[('OLD','SELL')],3)
            self.assertEqual(orders[('NEW','BUY')],12)
            self.assertEqual(store.read(),state)
            self.assertFalse(result['executable'])
            defensive = preview_target_weights(weights={},**args)
            self.assertEqual([(o['side'],o['quantity']) for o in defensive['difference']['new_orders']],[('SELL',3)])
            with self.assertRaisesRegex(ValueError,'STALE_REVISION'):
                preview_target_weights(weights={},**dict(args,expected_revision='old'))
            with self.assertRaises(ValueError):
                preview_target_weights(weights={'NEW':'1'},**dict(args,now='2026-11-06T14:35:00Z'))

            # Simulated execution through the real public store interface.
            # The ledger reports proceeds but intentionally requires a fresh
            # absolute broker cash confirmation before generating new advice.
            old_revision = state['revision']
            fill = dict(event_id='simulated-old-sale',kind='DIRECT_FILL',
                        security_id='OLD',side='SELL',quantity=orders[('OLD','SELL')],
                        price='100',fees='2',executed_at='2026-11-06T14:30:30+00:00')
            after_fill, effect = store.append(fill,expected_revision=old_revision)
            self.assertEqual(effect['cash_delta'],'298')
            self.assertEqual(after_fill['shares']['OLD'],0)
            self.assertFalse(after_fill['cash_confirmation_valid'])
            self.assertEqual(after_fill['total_uninvested_cash'],state['total_uninvested_cash'])
            with self.assertRaisesRegex(ValueError,'CASH_RECONFIRMATION_REQUIRED'):
                preview_target_weights(weights={'NEW':'1'},**dict(args,account=after_fill,expected_revision=after_fill['revision']))
            retried, _ = store.append(fill,expected_revision=old_revision)
            self.assertEqual(retried,after_fill)
            self.assertEqual(len(retried['events']),len(state['events'])+1)
            confirmed, _ = store.append(dict(event_id='post-sale-cash',kind='CASH_CONFIRM',
                amount='1548',cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=after_fill['revision'])
            next_result = preview_target_weights(weights={'NEW':'1'},**dict(args,account=confirmed,expected_revision=confirmed['revision']))
            self.assertEqual(next_result['target_quantities'],{'NEW':15})
            self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in next_result['difference']['new_orders']], [('NEW','BUY',15)])
            self.assertEqual(confirmed['available_cash'],'1548')
            self.assertFalse(confirmed['orders'])
            late_retry, _ = store.append(fill,expected_revision=old_revision)
            self.assertEqual(late_retry,confirmed)
            self.assertEqual(store.read(),confirmed)
if __name__ == '__main__': unittest.main()
