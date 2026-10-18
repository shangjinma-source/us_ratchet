"""Real adopted market -> next scheduled phase, with isolated synthetic data."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_run_real_monthly_release_update as update_fixture
from test_materialize_real_monthly_successor import extended_fixture
from scripts import run_rolling_real_monthly_update as runner


def two_month_fixture(folder):
    root, arguments, calls, bootstrap = extended_fixture(folder)
    def save(path, value):
        raw = json.dumps(value).encode(); (root/path).write_bytes(raw)
        return sha256(raw).hexdigest()
    config = json.loads((root/'coordinator.json').read_bytes())
    settings = json.loads((root/'settings.json').read_bytes())
    schedule = json.loads((root/'schedule.json').read_bytes())
    for day in ('2027-01-29', '2027-02-01'):
        schedule['calendar'].append(day)
        schedule['sessions'].append(dict(date=day, timezone='America/New_York',
            open_at=day+'T09:30:00-05:00', close_at=day+'T16:00:00-05:00'))
    settings['fixed_source_hashes']['schedule.json'] = save('schedule.json', schedule)
    config['settings_sha256'] = save('settings.json', settings)
    arguments['coordinator_sha256'] = save('coordinator.json', config)
    return root, arguments, calls, bootstrap


class RollingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = update_fixture.UpdateTests()
        with patch('test_build_real_monthly_release_entry.fixture', two_month_fixture):
            self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.now = self.fixture.now
        self.save = self.fixture.save
        pins = {}
        for name in runner.REQUIRED_SOURCE_PATHS:
            raw = (Path(__file__).resolve().parents[1]/name).read_bytes()
            target = self.root/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        digest = lambda name: sha256((self.root/name).read_bytes()).hexdigest()
        child = dict(schema='SCHEDULED_REAL_MONTHLY_UPDATE_V1', root=str(self.root),
            coordinator_config='coordinator.json', coordinator_sha256=digest('coordinator.json'),
            bootstrap_config='bootstrap.json', bootstrap_sha256=digest('bootstrap.json'),
            policy_path='policy.json', policy_sha256=digest('policy.json'),
            descriptor_path='approved.json', descriptor_sha256=digest('approved.json'),
            market_output_directory='real-market', update_output_directory='update', run_directory='runs', source_pins=pins)
        child_hash = self.save('scheduled.json', child)
        self.configuration = dict(schema='ROLLING_REAL_MONTHLY_UPDATE_V1', root=str(self.root),
            scheduled_config='scheduled.json', scheduled_sha256=child_hash, output_directory='chain', source_pins=pins)
        self.config_hash = self.save('rolling.json', self.configuration)

    def run_chain(self, execute=False):
        return runner.run(config_path=self.root/'rolling.json', config_sha256=self.config_hash,
                          execute=execute, clock=lambda:self.now)

    def adopt(self):
        return update_fixture.run(**self.fixture.args, execute=True)

    def test_real_adoption_to_next_phase_and_no_late_catchup(self):
        self.adopt()
        account = self.fixture.store.path.read_bytes()
        with patch('socket.socket', side_effect=AssertionError('NO_NETWORK')):
            self.assertEqual(self.run_chain()['status'], 'NEXT_MONTH_READY')
            self.assertFalse((self.root/'chain').exists())
            result = self.run_chain(True)
            self.assertEqual(result['status'], 'WAITING_SESSION_CLOSE')
            self.assertEqual(result['completed_months'], ['2026-12'])
            self.assertEqual(self.run_chain(True), result)
            self.now = datetime.fromisoformat('2027-01-01T16:00:00+00:00')
            result = self.run_chain(True)
            self.assertEqual(result['status'], 'MISSED_PREPARATION_WINDOW')
            self.assertFalse((self.root/'chain/2026-12/market').exists())
        self.assertEqual(self.fixture.store.path.read_bytes(), account)
        self.assertFalse((self.root/'data/strategy_account/monthly_targets.sqlite3').exists())

    def test_exclusive_lock_and_unapproved_code_rejected(self):
        (self.root/'chain').mkdir()
        (self.root/'chain/running.lock').write_text('{}')
        with patch.object(runner, 'scheduled', side_effect=AssertionError('NO_DISPATCH')):
            with self.assertRaises(FileExistsError): self.run_chain(True)
        (self.root/'chain/running.lock').unlink()
        (self.root/'scripts/materialize_real_monthly_successor.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'): self.run_chain(True)

    def test_nested_waiting_review_exposed_immediately(self):
        with patch.object(runner, 'scheduled', return_value=dict(status='MARKET_PREPARATION_PHASE',
                preparation=dict(status='WAITING_REVIEW'))):
            self.assertEqual(self.run_chain(True)['status'], 'WAITING_REVIEW')

    def test_partial_or_tampered_child_never_overwritten(self):
        self.adopt()
        self.run_chain(True)
        child = self.root/'chain/2026-12/scheduled.json'
        raw = child.read_bytes()
        child.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'): self.run_chain(True)
        child.write_bytes(raw)
        (self.root/'chain/2026-12/chain.complete.json').unlink()
        with self.assertRaisesRegex(ValueError, 'PARTIAL_CHAIN_NO_RETRY'): self.run_chain(True)

    def test_two_real_adoptions_traverse_history_without_readopting_old_month(self):
        from core.strategy_account_ledger import canonical
        from data.strategy_account_identity import PinnedStrategyIdentity
        from data.strategy_account_market_capture import StrategyAccountMarketCapture
        from data.strategy_account_action_capture import StrategyAccountActionCapture
        from data.current_quantity_v2_paper_action_sources import daily_url
        from scripts.run_real_monthly_market_preparation import run as produce
        self.adopt()
        self.run_chain(True)
        child = json.loads((self.root/'chain/2026-12/scheduled.json').read_bytes())
        manifest = json.loads((self.root/'prepared/manifest.json').read_bytes())
        chart_document = json.loads((self.root/manifest['candidates'][0]['training_source']).read_bytes())
        chart = chart_document['chart']['result'][0]
        schedule = json.loads((self.root/'schedule.json').read_bytes())
        for day in schedule['calendar']:
            if manifest['decision_date'] < day <= '2026-12-31':
                chart['timestamp'].append(int(datetime.fromisoformat(day+'T21:00:00+00:00').timestamp()))
                for values in chart['indicators']['quote'][0].values():
                    values.append(values[-1]+1)
        self.now = datetime.fromisoformat('2026-12-31T22:00:00+00:00')
        arguments = {key:child[key] for key in ('coordinator_config','coordinator_sha256','bootstrap_config',
                      'bootstrap_sha256','policy_path','policy_sha256')}
        arguments['coordinator_config'] = self.root/arguments['coordinator_config']
        arguments['bootstrap_config'] = self.root/arguments['bootstrap_config']
        rss = b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Thu, 31 Dec 2026 21:30:00 GMT</pubDate></item></channel></rss>'
        produced = produce(**arguments, output_directory=child['market_output_directory'], execute=True, clock=lambda:self.now,
            fetch=lambda url, **kw: dict(raw=canonical(chart_document), http_status=200, final_url=url, response_headers={}),
            rss_fetch=lambda:dict(status=200, body=rss))
        self.assertEqual(produced['status'], 'MARKET_PUBLICATION_READY_NOT_ACTIVATED')
        self.now = datetime.fromisoformat('2027-01-01T15:00:00+00:00')
        identity = PinnedStrategyIdentity(self.root, produced['identity_manifest'], produced['identity_sha256'])
        def fetch(ticker):
            start = int(datetime.fromisoformat('2027-01-01T14:30:00+00:00').timestamp()); last = start+1800
            return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',
                exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=last,
                currentTradingPeriod=dict(regular=dict(start=start,end=start+23400))),timestamp=[last-60],
                indicators=dict(quote=[dict(open=[10],high=[11],low=[9],close=[10],volume=[10])]))])))
        market = StrategyAccountMarketCapture(identity_resolver=identity, fetch=fetch, clock=lambda:self.now)
        action = StrategyAccountActionCapture(clock=lambda:self.now,
            fetch=lambda t,s,e:dict(status=200,url=daily_url(t,s,e),body=canonical(dict(chart=dict(error=None,result=[
                dict(meta=dict(symbol=t,currency='USD',instrumentType='EQUITY'),events={})])))),
            rss_fetch=lambda:dict(status=200,body=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated</title><pubDate>Fri, 01 Jan 2027 14:00:00 GMT</pubDate></item></channel></rss>'))
        complete_path = child['market_output_directory']+'/complete.json'
        update = update_fixture.run(root=self.root, complete_path=complete_path,
            complete_sha256=sha256((self.root/complete_path).read_bytes()).hexdigest(), descriptor_path=child['descriptor_path'],
            descriptor_sha256=child['descriptor_sha256'], output_directory=child['update_output_directory'],
            execute=True, clock=lambda:self.now, market_capture=market, action_capture=action)
        self.assertEqual(update['release_revision'], 2)
        before = self.fixture.store.path.read_bytes()
        with patch('scripts.run_real_monthly_release_update.MonthlyReleaseActivation.adopt', side_effect=AssertionError('OLD_ADOPTION_REPEATED')):
            result = self.run_chain(True)
            self.assertEqual(result['completed_months'], ['2026-12','2027-01'])
            self.assertEqual(result['status'], 'WAITING_SESSION_CLOSE')
            self.assertEqual(self.run_chain(True), result)
        self.assertEqual(self.fixture.store.path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
