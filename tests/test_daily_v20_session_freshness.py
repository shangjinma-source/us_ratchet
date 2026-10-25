"""Cross-session evidence admission, using real readers/provider in temp roots."""
from datetime import datetime,timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import json
from unittest.mock import Mock

from core.strategy_account_ledger import canonical
from data.strategy_daily_domain_packet_reader_v2 import DomainSessionDailyPacketReaderV2
import test_daily_recent_minute_retry_v1 as previews
import test_strategy_daily_dynamic_factory_v5 as packets


class SessionFreshnessTests(unittest.TestCase):
    def test_fresh_verified_signal_with_previous_session_quote_is_rejected(self):
        from data.strategy_account_market_capture import StrategyAccountMarketCapture
        with TemporaryDirectory() as folder:
            c=previews.RecentMinuteRetryTests().setup(folder)
            class Identity:
                def __call__(self,ticker):return dict(ticker=ticker,security_id={'AAA':'A','BBB':'B'}[ticker],source_references=['identity-only'],source_hashes={'identity-only':sha256(b'id').hexdigest()})
                def _read(self,path,digest):return b'id'
            def old_quote(ticker):
                document=json.loads(c.raw(ticker));row=document['chart']['result'][0]
                row['timestamp']=[t-86400 for t in row['timestamp']]
                row['meta']['regularMarketTime']-=86400
                for key in ('start','end'):row['meta']['currentTradingPeriod']['regular'][key]-=86400
                return canonical(document)
            c.provider.market=StrategyAccountMarketCapture(identity_resolver=Identity(),fetch=old_quote,clock=lambda:c.clock[0])
            before=c.store.path.read_bytes()
            with self.assertRaises(ValueError):
                c.service.preview(expected_revision=c.state['revision'],target_id=c.target['target_id'])
            self.assertEqual(c.sleeps,[]);self.assertEqual(c.store.path.read_bytes(),before)

    def test_v7_archived_yesterday_signal_never_fetches_today_quote(self):
        with TemporaryDirectory() as folder:
            c=previews.RecentMinuteRetryTests().setup(folder)
            before=c.store.path.read_bytes();target=c.monthly.current()
            c.clock[0]+=timedelta(days=1)
            c.provider.market.capture=Mock(side_effect=AssertionError('old signal must not capture'))
            result=c.service.preview(expected_revision=c.state['revision'],target_id=c.target['target_id'])
            self.assertEqual((result['status'],result['reason']),('WAIT','WAIT_NEW_SESSION_EVIDENCE'))
            self.assertEqual(result['new_orders'],[]);self.assertEqual(result['reference_quotes'],{})
            c.provider.market.capture.assert_not_called()
            self.assertEqual(c.sleeps,[]);self.assertEqual(c.store.path.read_bytes(),before);self.assertEqual(c.monthly.current(),target)

    def test_real_session_close_during_sleep_never_revives_orders(self):
        with TemporaryDirectory() as folder:
            c=previews.RecentMinuteRetryTests().setup(folder)
            # Genuine fixed calendar and verified parent expire at21:00 UTC.
            c.clock[0]=datetime.fromisoformat('2026-11-02T20:59:00.500000+00:00')
            original=c.provider.limits
            def processing_delay(**kwargs):
                # Model real source/unit-review elapsed time, within120seconds.
                c.clock[0]=datetime.fromisoformat('2026-11-02T20:59:59.200000+00:00')
                return original(**kwargs)
            c.provider.limits=processing_delay
            before=c.store.path.read_bytes()
            with self.assertRaisesRegex(ValueError,'DAILY_SIGNAL_EXPIRED_BEFORE_RECAPTURE'):
                c.service.preview(expected_revision=c.state['revision'],target_id=c.target['target_id'])
            self.assertEqual(c.round,1);self.assertEqual(c.sleeps,[2])
            self.assertEqual(c.store.path.read_bytes(),before)

    def test_current_domain_requires_today_full_packet_not_yesterday_copy(self):
        with TemporaryDirectory() as folder:
            c,root,config,run,calls=packets.MigrationFactoryTests().setup(folder)
            raw=canonical(config);(root/'session-reader.json').write_bytes(raw)
            reader=DomainSessionDailyPacketReaderV2(root=root,configuration_path='session-reader.json',
                configuration_sha256=sha256(raw).hexdigest(),archive_root=None)
            self.assertEqual(run()['status'],'DYNAMIC_DOMAIN_PACKET_SAVED')
            prior=root/config['runs_root']/'2026-11-03'/'terminal.json'
            prior_bytes=prior.read_bytes();before=c.store.path.read_bytes()
            c.clock[0]=datetime.fromisoformat('2026-11-04T15:00:00+00:00')
            missing=reader(c.store.read(),c.target,c.clock[0])
            self.assertEqual((missing['status'],missing['reason']),('WAIT_SIGNAL','WAIT_NEW_SESSION_EVIDENCE'))
            # Only this deliberately-invalid temp fixture is removed afterward;
            # production failed packets are never deleted or rewritten.
            today=root/config['runs_root']/'2026-11-04';today.mkdir()
            forged=today/'terminal.json';forged.write_bytes(prior_bytes)
            with self.assertRaises((ValueError,OSError)):
                reader(c.store.read(),c.target,c.clock[0])
            forged.unlink();today.rmdir()
            self.assertEqual(run()['status'],'DYNAMIC_DOMAIN_PACKET_SAVED')
            admitted=reader(c.store.read(),c.target,c.clock[0])
            self.assertEqual(admitted['status'],'WAIT_POLICY_RELEASE')
            self.assertIsNone(admitted['signal'])
            self.assertEqual(calls,['BBB','BBB'])
            self.assertEqual(prior.read_bytes(),prior_bytes);self.assertEqual(c.store.path.read_bytes(),before)

if __name__=='__main__':unittest.main()
