"""Same live reader across opening, isolated fixtures only; no production clock edits."""
from datetime import datetime
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_continuous32_target_decision import PROFILE_ID, VERSION
from data.strategy_daily_domain_policy_reader_v2 import REVIEW_SOURCES
from data.strategy_monthly_supplement_reader import MonthlySupplementReader, EXTRA_SOURCES
from data.monthly_peak_exit_store import MonthlyPeakExitStore
import test_strategy_daily_dynamic_factory_v5 as fixtures

ROOT = Path(__file__).resolve().parents[1]


class SupplementReaderTests(unittest.TestCase):
    def publish_target(self, c, root, original_target, arguments):
        from data.strategy_continuous32_target_decision import decide_target
        decision = decide_target(state=c.store.read(), now=c.clock[0].isoformat(),
            maximum_mark_age_seconds=900, **arguments)
        c.target = deepcopy(original_target)
        c.target['payload'].update(decision=decision, target_quantities=decision['payload']['target_quantities'],
            created_at=c.clock[0].isoformat())
        c.target['target_id'] = sha256(canonical(c.target['payload'])).hexdigest()

    def verify_advice_http(self, c, risk_reader):
        pass  # Extended by the capital HTTP integration fixture.

    def test_premarket_wait_does_not_latch_after_open_or_rewrite_source(self):
        with TemporaryDirectory() as folder:
            c, root, source, run, calls = fixtures.MigrationFactoryTests().setup(folder)
            c.clock[0] = datetime.fromisoformat('2026-11-03T14:29:00+00:00')
            self.assertEqual(run()['status'], 'DYNAMIC_DOMAIN_PACKET_SAVED')
            source_raw = canonical(source)
            (root/'source-reader.json').write_bytes(source_raw)
            source_ref = dict(path='source-reader.json', sha256=sha256(source_raw).hexdigest())
            pins = []
            for name in sorted(REVIEW_SOURCES | EXTRA_SOURCES):
                body = (ROOT/name).read_bytes()
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
                pins.append(dict(path=name, sha256=sha256(body).hexdigest()))
            release_document = json.loads((root/'release.json').read_bytes())
            self.assertTrue(release_document['fixture_only'])
            # The source fixture extends its one-session calendar for rolling
            # capture; its isolated policy must bind that extended calendar too.
            release_document['calendar_sha256'] = source['calendar']['sha256']
            release = canonical(release_document)
            (root/'release.json').write_bytes(release)
            config = dict(schema='SERVER_DOMAIN_POLICY_APPLICATION_REVIEW_V1', authorized=True,
                scope='COMPLETE_CURRENT_SESSION_DOMAIN', account_id=c.store.read()['account_id'],
                selector_profile=PROFILE_ID, selection_method=VERSION, continuous_iterations=32,
                authorization_id='FIXTURE_ONLY_OPEN_TRANSITION', authorization_source='ISOLATED_TEST',
                rule_selection_role='IMPLEMENTER_RECOMMENDATION_REVIEWED',
                authorized_at='2026-11-02T14:00:00Z', valid_from='2026-11-02T14:00:00Z',
                valid_until='2026-11-04T21:00:00Z', source_configuration=source_ref,
                calendar=source['calendar'], release=dict(path='release.json',sha256=sha256(release).hexdigest()),
                code_pins=pins, archive_root=getattr(self, 'policy_archive_root', 'policy-archive'), fixture_only=True,
                monthly_supplement=dict(schema='CURRENT_SESSION_MONTHLY_SUPPLEMENT_V1', authorized=True, capture_root='supplements'))
            raw = canonical(config)
            (root/'policy-review.json').write_bytes(raw)
            reader = MonthlySupplementReader(account_reader=c.store.read, target_reader=lambda:c.target,
                risk_store=MonthlyPeakExitStore(root/'risk.sqlite'),root=root, configuration_path=source_ref['path'],
                configuration_sha256=source_ref['sha256'], archive_root=None,
                review_configuration_path='policy-review.json', review_configuration_sha256=sha256(raw).hexdigest(),
                clock=lambda:c.clock[0])
            before = c.store.path.read_bytes()
            terminal = root/source['runs_root']/'2026-11-03'/'terminal.json'
            terminal_before = terminal.read_bytes()
            wait = reader(c.store.read(), c.target, c.clock[0])
            self.assertEqual(wait['reason'], 'WAIT_POLICY_REVIEW_SESSION')
            self.assertIsNone(wait['signal'])
            self.assertFalse((root/config['archive_root']).exists())
            c.clock[0] = datetime.fromisoformat('2026-11-03T14:30:00+00:00')
            opened = reader(c.store.read(), c.target, c.clock[0])
            self.assertEqual(opened['status'], 'DAILY_SIGNAL_READY')
            self.assertTrue(Path(opened['evidence_archive']['complete_path']).is_file())
            original_target = c.target
            added = deepcopy(c.target)
            added['payload']['target_quantities']['A'] = 1
            decision = added['payload']['decision']
            decision['payload']['target_quantities']['A'] = 1
            decision['decision_id'] = sha256(canonical(decision['payload'])).hexdigest()
            added['target_id'] = sha256(canonical(added['payload'])).hexdigest()
            c.target = added
            missing = reader(c.store.read(), c.target, c.clock[0])
            self.assertEqual(missing['reason'], 'WAIT_UNIT_BASELINE')
            self.assertIsNone(missing['signal'])
            self.assertFalse((root/'supplements').exists())
            c.target = original_target
            reader.account_reader = lambda: dict(c.store.read(), revision='changed-during-refresh')
            with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_SNAPSHOT_CHANGED'):
                reader(c.store.read(), c.target, c.clock[0])
            reader.account_reader = c.store.read
            # Establish the real monthly risk epoch before same-day reconfiguration.
            from data.monthly_cap_exit_reader_v2 import MonthlyCapExitReaderV2
            risk_reader = MonthlyCapExitReaderV2(source_reader=reader, risk_store=reader.risk_store,
                source_archive_root=root/config['archive_root'], output_archive_root=root/'risk-archive',
                release_bytes=getattr(self, 'cap_release_bytes', b'isolated-cap-release'), validate_release=lambda: None)
            risk_reader(c.store.read(), c.target, c.clock[0])
            from data.strategy_account_identity import PinnedStrategyIdentity
            from data.strategy_account_market_capture import StrategyAccountMarketCapture
            from data.strategy_continuous32_target_decision import decide_target, REQUIRED_PINS
            resolver = PinnedStrategyIdentity(root, c.identity_reference['path'], c.identity_reference['sha256'])
            c.store.append(dict(event_id='isolated-new-a', kind='DIRECT_FILL', security_id='A', side='BUY',
                quantity=1, price='100', fees='0', executed_at=c.clock[0].isoformat(), identity_evidence=resolver('AAA')),
                expected_revision=c.store.read()['revision'])
            c.store.append(dict(event_id='isolated-new-cash', kind='CASH_CONFIRM', amount='100',
                cash_basis='TOTAL_UNINVESTED'), expected_revision=c.store.read()['revision'])
            # A completed regular-session window, required by buy-limit review.
            c.clock[0] = datetime.fromisoformat('2026-11-03T15:00:00+00:00')
            def minute_raw(ticker):
                last = int(c.clock[0].timestamp()); start = last-1800
                return canonical(dict(chart=dict(error=None, result=[dict(meta=dict(symbol=ticker,
                    currency='USD', instrumentType='EQUITY', exchangeTimezoneName='America/New_York',
                    dataGranularity='1m', regularMarketPrice=100, regularMarketTime=last,
                    currentTradingPeriod=dict(regular=dict(start=start,end=start+23400))),
                    timestamp=list(range(start,last,60)), indicators=dict(quote=[dict(open=[100]*30, high=[101]*30, low=[99]*30,
                    close=[100]*30, volume=[10]*30)]))])))
            c.provider.market = StrategyAccountMarketCapture(identity_resolver=resolver,
                fetch=minute_raw, clock=lambda:c.clock[0], max_mark_age=120)
            state = c.store.read(); arguments = c.provider.selection(state)
            for name in REQUIRED_PINS:
                body = (ROOT/name).read_bytes()
                arguments['source_package']['files'][name] = body
                arguments['source_package']['source_hashes'][name] = sha256(body).hexdigest()
            capture_calls = []
            calendar = json.loads((root/source['calendar']['path']).read_bytes())
            days = [row['date'] for row in calendar['sessions']]
            index = days.index('2026-11-03'); window = calendar['sessions'][index-20:index]
            def daily(ticker, *args):
                capture_calls.append(ticker)
                return dict(status=200, body=canonical(dict(chart=dict(error=None, result=[dict(
                    meta=dict(symbol=ticker, currency='USD', instrumentType='EQUITY', exchangeName='NMS'), events={},
                    timestamp=[int(datetime.fromisoformat(row['open']).timestamp()) for row in window],
                    indicators=dict(quote=[dict(close=[100]*20)], adjclose=[dict(adjclose=[100]*20)]))]))))
            reader.fetch_daily = daily
            reader.fetch_official = lambda: dict(status=200, body=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>')
            c.risk_reader = risk_reader
            self.publish_target(c, root, original_target, arguments)
            before = c.store.path.read_bytes()
            supplemented = risk_reader(c.store.read(), c.target, c.clock[0])
            self.assertEqual(supplemented['status'], 'DAILY_SIGNAL_READY')
            expected_captures = getattr(self, 'expected_supplement_captures', ['AAA'])
            self.assertEqual(capture_calls, expected_captures)
            risk_reader(c.store.read(), c.target, c.clock[0])
            self.assertEqual(capture_calls, expected_captures)
            self.verify_advice_http(c, risk_reader)
            self.assertEqual(c.store.path.read_bytes(), before)
            handoff = getattr(self, 'verify_fill_handoff', None)
            if handoff:
                handoff(c, risk_reader)
                before = c.store.path.read_bytes()
            c.clock[0] = datetime.fromisoformat('2026-11-03T21:00:00+00:00')
            closed = reader(c.store.read(), c.target, c.clock[0])
            self.assertEqual(closed['reason'], 'WAIT_NEXT_SESSION')
            self.assertIsNone(closed['signal'])
            self.assertEqual(calls, ['BBB'])
            self.assertEqual(c.store.path.read_bytes(), before)
            self.assertEqual(terminal.read_bytes(), terminal_before)


if __name__ == '__main__':
    unittest.main()
