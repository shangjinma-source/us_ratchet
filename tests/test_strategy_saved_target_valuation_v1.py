from tempfile import TemporaryDirectory
from datetime import timedelta
from unittest.mock import patch
from hashlib import sha256
import unittest
import test_unified_publication_guard_v7 as fixture
from data.strategy_saved_target_valuation_v1 import SnapshotValuationServiceV1


class SavedValuationTests(unittest.TestCase):
    def setup_case(self,folder):
        c,monthly,prepared=fixture.UnifiedPublicationGuardTests().setup_case(folder)
        service=SnapshotValuationServiceV1(monthly=monthly,root=monthly.root,
            calendar_reference=dict(path='calendar.json',sha256=sha256((monthly.root/'calendar.json').read_bytes()).hexdigest()),
            validate_sources=prepared['validate_code'],clock=lambda:c.clock[0])
        runtime,_=monthly._for_target(monthly.current())
        return c,monthly,service,runtime.execution_provider.__self__

    def test_real_capture_no_training_or_execution_and_unlocked(self):
        with TemporaryDirectory() as folder:
            c,monthly,service,provider=self.setup_case(folder)
            sid=next(sid for sid,q in monthly.accounts.read()['shares'].items() if q)
            ticker='AAA' if sid=='A' else 'BBB'
            identity=monthly.resolve_identity(ticker)
            monthly.accounts.append(dict(event_id='unconfirmed-fill',kind='DIRECT_FILL',security_id=sid,side='BUY',quantity=1,price='100',fees='0',executed_at=c.clock[0].isoformat(),identity_evidence=identity),expected_revision=monthly.accounts.read()['revision'])
            self.assertFalse(monthly.accounts.read()['cash_confirmation_valid'])
            capture=provider.market.capture
            def checked_capture(**kwargs):
                self.assertFalse(monthly.lock._is_owned())
                return capture(**kwargs)
            before=monthly.accounts.path.read_bytes();target_before=monthly.targets.path.read_bytes()
            with patch.object(provider.market,'capture',side_effect=checked_capture),patch.object(provider,'training',side_effect=AssertionError('no compile')),patch.object(provider,'execution',side_effect=AssertionError('no execution')),patch.object(provider,'limits',side_effect=AssertionError('no limits')):
                result=service.valuation(expected_revision=monthly.accounts.read()['revision'])
            self.assertEqual(result['status'],'READY');self.assertTrue(result['holdings']);self.assertFalse(result['cash_confirmed']);self.assertIsNone(result['strategy_total'])
            self.assertEqual(monthly.accounts.path.read_bytes(),before);self.assertEqual(monthly.targets.path.read_bytes(),target_before)

    def test_account_change_during_capture_rejected(self):
        with TemporaryDirectory() as folder:
            c,monthly,service,provider=self.setup_case(folder)
            capture=provider.market.capture
            def changed(**kwargs):
                result=capture(**kwargs)
                monthly.accounts.append(dict(event_id='cash-race',kind='CASH_CONFIRM',amount='10',cash_basis='AVAILABLE_AFTER_RESERVATIONS'),expected_revision=monthly.accounts.read()['revision'])
                return result
            with patch.object(provider.market,'capture',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'SNAPSHOT_CHANGED'):service.valuation()

    def test_target_source_and_completion_expiry_rejected(self):
        for mode in ('source','expiry'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                c,monthly,service,provider=self.setup_case(folder)
                assemble=provider._assemble
                def changed(*args,**kwargs):
                    result=assemble(*args,**kwargs)
                    if mode=='source':
                        path=provider.root/provider.manifest_path
                        path.write_bytes(path.read_bytes()+b' ')
                    else:c.clock[0]+=timedelta(seconds=121)
                    return result
                with patch.object(provider,'_assemble',side_effect=changed):
                    with self.assertRaises(ValueError):service.valuation()

    def test_missing_target_and_empty_holdings_explicit(self):
        with TemporaryDirectory() as folder:
            c,monthly,service,provider=self.setup_case(folder)
            with patch.object(monthly,'current',return_value=None),patch.object(provider.market,'capture',side_effect=AssertionError('no capture')):
                self.assertEqual(service.valuation()['status'],'WAIT_SAVED_TARGET')
            for sid,quantity in list(monthly.accounts.read()['shares'].items()):
                if quantity:
                    identity=monthly.resolve_identity('AAA' if sid=='A' else 'BBB')
                    monthly.accounts.append(dict(event_id='empty-'+sid,kind='DIRECT_FILL',security_id=sid,side='SELL',quantity=quantity,price='100',fees='0',executed_at=c.clock[0].isoformat(),identity_evidence=identity),expected_revision=monthly.accounts.read()['revision'])
            with patch.object(provider.market,'capture',side_effect=AssertionError('no capture')):
                self.assertEqual(service.valuation()['status'],'EMPTY_HOLDINGS')

    def test_outside_session_does_not_capture(self):
        with TemporaryDirectory() as folder:
            c,monthly,service,provider=self.setup_case(folder)
            c.clock[0]=c.clock[0].replace(hour=22)
            with patch.object(provider.market,'capture',side_effect=AssertionError('must not capture')):
                self.assertEqual(service.valuation()['status'],'WAIT_REGULAR_SESSION')

if __name__=='__main__':unittest.main()
