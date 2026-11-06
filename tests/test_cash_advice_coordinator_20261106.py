from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from api.strategy_account import StrategyAccountService, WriteOutcomeUncertain
from docs.candidates.frozen_target_provider_20261106 import digest
from docs.candidates.frozen_target_builder_20261106 import FrozenTargetBuilder
from docs.candidates.cash_advice_coordinator_20261106 import CashAdviceCoordinator


class CoordinatorTests(unittest.TestCase):
    def test_uncertain_response_after_durable_write_reconciles_once(self):
        with TemporaryDirectory() as directory:
            now=datetime.fromisoformat('2026-11-06T14:31:00+00:00')
            account=StrategyAccountService(database_path=Path(directory)/'account.sqlite3',
                account_id='test',resolver=lambda ticker:None,clock=lambda:now)
            initial=account.initialize({'event_id':'init'})['account']
            body=dict(expected_revision=initial['revision'],event=dict(event_id='cash',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'))
            append=account.append
            def committed_then_failed(value):
                append(value)
                raise WriteOutcomeUncertain()
            account.append=Mock(side_effect=committed_then_failed)
            builder=Mock()
            builder.rebuild.side_effect=lambda:dict(account_revision=account.store.read()['revision'],target_id='a'*64,proposal_id='b'*64)
            builder.preview.return_value={'executable':False}
            result=CashAdviceCoordinator(account_service=account,builder=builder).save_cash(body)
            self.assertTrue(result['cash_saved']);self.assertTrue(result['advice_ready'])
            self.assertEqual(len(account.store.read()['events']),1)
            account.append.assert_called_once_with(body)
            builder.rebuild.assert_called_once()

    def test_uncertain_unconfirmed_or_unreadable_write_stays_unknown(self):
        event=dict(event_id='cash',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED')
        body=dict(expected_revision='a'*64,event=event)
        outcomes=[{'revision':'b'*64,'events':[]},
                  {'revision':'b'*64,'events':[{'payload':dict(event,amount='999')}]},
                  None,OSError('unreadable')]
        for outcome in outcomes:
            with self.subTest(outcome=type(outcome).__name__):
                account=Mock();account.append.side_effect=WriteOutcomeUncertain()
                if isinstance(outcome,Exception):account.store.read.side_effect=outcome
                else:account.store.read.return_value=outcome
                builder=Mock()
                result=CashAdviceCoordinator(account_service=account,builder=builder).save_cash(body)
                self.assertIsNone(result['cash_saved']);self.assertFalse(result['advice_ready'])
                self.assertEqual(result['reason'],'CASH_WRITE_REQUIRES_RECONCILIATION')
                builder.rebuild.assert_not_called();account.append.assert_called_once_with(body)

    def test_commit_failure_retry_and_idempotence(self):
        with TemporaryDirectory() as directory:
            now=datetime.fromisoformat('2026-11-06T14:31:00+00:00')
            account=StrategyAccountService(database_path=Path(directory)/'account.sqlite3',
                account_id='test',resolver=lambda ticker:None,clock=lambda:now)
            initial=account.initialize({'event_id':'init'})['account']
            policy=dict(strategy_epoch='test',weights={'NEW':'1'},signal_at='2026-11-05T21:00:00Z',
                valid_from='2026-11-06T14:30:00Z',valid_until='2026-11-06T14:32:00Z')
            quote_calls=[];fail=[False]
            def quotes(state):
                quote_calls.append(state['revision'])
                if fail[0]: raise ValueError('QUOTE_UNAVAILABLE')
                return dict(marks={'NEW':dict(security_id='NEW',currency='USD',price_basis='current',price='100',observed_at=now.isoformat())},
                    limits={'NEW':dict(security_id='NEW',price_basis='current',buy='100',sell='100',observed_at=now.isoformat())})
            builder=FrozenTargetBuilder(directory=Path(directory)/'targets',policy=policy,contract_sha256=digest(policy),
                expected_epoch='test',account_id='test',store=account.store,quote_provider=quotes,clock=lambda:now)
            coordinator=CashAdviceCoordinator(account_service=account,builder=builder)
            first=dict(expected_revision=initial['revision'],event=dict(event_id='cash1',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'))
            success=coordinator.save_cash(first)
            self.assertTrue(success['cash_saved']);self.assertTrue(success['advice_ready'])
            self.assertEqual(success['advice']['difference']['new_orders'][0]['quantity'],10)
            before=account.store.read()
            self.assertTrue(coordinator.save_cash(first)['advice_ready'])
            self.assertEqual(account.store.read(),before)
            second=dict(expected_revision=before['revision'],event=dict(event_id='cash2',kind='CASH_CONFIRM',amount='3000',cash_basis='TOTAL_UNINVESTED'))
            fail[0]=True
            failed=coordinator.save_cash(second)
            self.assertTrue(failed['cash_saved']);self.assertFalse(failed['advice_ready'])
            saved=account.store.read()
            self.assertEqual(saved['available_cash'],'3000')
            self.assertEqual(failed['account_revision'],saved['revision'])
            fail[0]=False
            recovered=coordinator.retry_advice()
            self.assertTrue(recovered['advice_ready'])
            self.assertEqual(recovered['advice']['difference']['new_orders'][0]['quantity'],30)
            self.assertEqual(account.store.read(),saved)
            calls=len(quote_calls)
            invalid=dict(expected_revision=initial['revision'],event=dict(event_id='invalid',kind='CASH_CONFIRM',amount='500',cash_basis='TOTAL_UNINVESTED'))
            with self.assertRaises(ValueError): coordinator.save_cash(invalid)
            self.assertEqual(len(quote_calls),calls)
            self.assertEqual(account.store.read(),saved)


if __name__ == '__main__': unittest.main()
