from copy import deepcopy
from hashlib import sha256
from threading import RLock
import unittest
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_account_runtime import RUNTIME_PATHS
from data.strategy_account_archived_holding_charts import ArchivedHoldingCharts
import test_strategy_monthly_target_charts as chart_fixture


class ArchivedHoldingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = chart_fixture.ChartsTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.accounts = StrategyAccountStore(self.root/'account.sqlite3')
        self.accounts.initialize('real',operation_id='init')
        state = self.accounts.read()
        self.accounts.append(dict(event_id='buy',kind='DIRECT_FILL',security_id='sid:AAA',side='BUY',
            quantity=2,price='12',fees='0',executed_at='2026-10-05T15:00:00Z',
            identity_evidence=dict(ticker='AAA',security_id='sid:AAA',source_references=['identity.json'],
                source_hashes={'identity.json':'2'*64})),expected_revision=state['revision'])
        self.targets = StrategyMonthlyTargetStore(self.root/'targets.sqlite3')
        self.configuration = dict(schema='REAL_STRATEGY_RUNTIME_V1',target_month='2026-10',
            training_manifest='manifest.json',training_sha256=sha256((self.root/'manifest.json').read_bytes()).hexdigest(),
            training_closed_at='2026-10-05T16:00:00-04:00',identity_manifest='identity.json',
            identity_sha256='2'*64,runtime_pins={p:'3'*64 for p in RUNTIME_PATHS})
        self.archive = dict(schema='REAL_STRATEGY_RUNTIME_ARCHIVE_V1',entries=[])
        self.add('old.json',self.configuration)

    def put(self,path,value):
        raw=canonical(value);(self.root/path).write_bytes(raw);return sha256(raw).hexdigest()

    def add(self,path,configuration):
        self.archive['entries'].append(dict(configuration_path=path,configuration_sha256=self.put(path,configuration)))

    def target(self,configuration,event_id):
        binding=dict(documents={'training_manifest':configuration['training_manifest']},
            source_hashes={configuration['training_manifest']:configuration['training_sha256'],
                           configuration['identity_manifest']:configuration['identity_sha256']})
        decision_payload=dict(input_binding=binding,input_id=sha256(canonical(binding)).hexdigest(),target_quantities={})
        previous=self.targets.current()
        return self.targets.append(dict(schema='REAL_STRATEGY_MONTHLY_TARGET_V1',account_id='real',
            target_month=configuration['target_month'],runtime_pins=configuration['runtime_pins'],
            request={'event_id':event_id},previous_target_id=previous['target_id'] if previous else None,
            target_quantities={},decision=dict(payload=decision_payload,decision_id=sha256(canonical(decision_payload)).hexdigest())))

    def charts(self,bootstrap=None,display_sources=None):
        return ArchivedHoldingCharts(root=self.root,account_store=self.accounts,account_id='real',
            target_store=self.targets,archive_path='archive.json',archive_sha256=self.put('archive.json',self.archive),
            shared_lock=RLock(),bootstrap_configuration=bootstrap,display_sources=display_sources)

    def test_independent_display_source_survives_archive_and_is_not_training(self):
        raw=deepcopy(self.fixture.raw)
        raw['chart']['result'][0]['meta'].update(exchangeName='NMS',fullExchangeName='NasdaqGS')
        digest=self.put('display.json',raw)
        sources={'sid:AAA':dict(ticker='AAA',path='display.json',sha256=digest,
            as_of='2026-10-06',captured_at='2026-10-07T00:00:00+00:00')}
        charts=self.charts(self.configuration,sources)
        sources['sid:AAA']['sha256']='0'*64
        before=self.accounts.path.read_bytes()
        for interval in ('day','week','month'):
            result=self.bars(charts,interval=interval)
            self.assertEqual(result['daily_as_of'],'2026-10-06')
            self.assertEqual(result['bars'][-1]['close'],100)
            self.assertTrue(result['display_source_independent'])
            self.assertTrue(result['execution_blocked'])
            self.assertEqual(result['training_manifest_sha256'],self.configuration['training_sha256'])
        self.assertEqual(before,self.accounts.path.read_bytes())
        self.assertFalse(self.targets.path.exists())
        (self.root/'display.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'CHART_SOURCE_CHANGED'):
            self.bars(charts)

    def bars(self,charts,**kwargs):
        return charts.bars(account_revision=self.accounts.read()['revision'],security_id='sid:AAA',**kwargs)

    def test_departed_holding_uses_old_target_complete_source_without_mutation(self):
        old=self.target(self.configuration,'old')
        empty=dict(decision_date='2026-11-02',candidates=[],source_hashes={})
        new=dict(self.configuration,target_month='2026-11',training_manifest='empty.json',training_sha256=self.put('empty.json',empty))
        self.add('new.json',new);self.target(new,'new')
        charts=self.charts()
        before={p.name:p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            result=self.bars(charts)
        self.assertEqual(result['source_target_id'],old['target_id'])
        self.assertTrue(result['historical_target_fallback'])
        self.assertEqual(result['daily_as_of'],'2026-10-05')
        self.assertEqual(len(result['bars']),4)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir() if p.is_file()})

    def test_current_target_preferred_and_bootstrap_without_target(self):
        charts=self.charts(self.configuration)
        self.assertIsNone(self.bars(charts)['source_target_id'])
        self.assertFalse(self.targets.path.exists())
        current=self.target(self.configuration,'current')
        result=self.bars(self.charts())
        self.assertEqual(result['source_target_id'],current['target_id'])
        self.assertFalse(result['historical_target_fallback'])
        self.assertEqual(len(self.bars(self.charts(),interval='week')['bars']),2)

    def test_missing_source_or_unapproved_bootstrap_rejected(self):
        with self.assertRaisesRegex(ValueError,'HOLDING_CHART_APPROVED_SOURCE_REQUIRED'):
            self.bars(self.charts())
        with self.assertRaisesRegex(ValueError,'RELEASE_RUNTIME_ARCHIVE_NOT_UNIQUE_OR_UNAVAILABLE'):
            self.bars(self.charts(dict(self.configuration,training_sha256='0'*64)))

    def test_current_identity_conflict_and_raw_drift_do_not_fallback(self):
        self.target(self.configuration,'old')
        import json
        manifest=json.loads((self.root/'manifest.json').read_bytes())
        manifest['candidates'][0]['ticker']='WRONG'
        new=dict(self.configuration,training_manifest='conflict.json',training_sha256=self.put('conflict.json',manifest))
        self.add('conflict-config.json',new);self.target(new,'conflict')
        with self.assertRaisesRegex(ValueError,'CHART_IDENTITY_MISMATCH'):
            self.bars(self.charts())
        # Use approved bootstrap in a separate empty journal, preserving the conflicting journal.
        self.targets=StrategyMonthlyTargetStore(self.root/'empty-targets.sqlite3')
        (self.root/'AAA.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'CHART_SOURCE_CHANGED'):
            self.bars(self.charts(self.configuration))

    def test_bootstrap_continues_after_first_target_excludes_existing_holding(self):
        self.assertEqual(self.bars(self.charts(self.configuration))['source_kind'],'BOOTSTRAP')
        empty=dict(decision_date='2026-11-02',candidates=[],source_hashes={})
        new=dict(self.configuration,target_month='2026-11',training_manifest='empty.json',
                 training_sha256=self.put('empty.json',empty))
        self.add('new.json',new);self.target(new,'first-target')
        result=self.bars(self.charts(self.configuration))
        self.assertEqual(result['source_kind'],'BOOTSTRAP')
        self.assertIsNone(result['source_target_id'])
        self.assertFalse(result['historical_target_fallback'])
        self.assertEqual(result['daily_as_of'],'2026-10-05')

    def test_account_or_target_change_during_read_is_rejected(self):
        from data.strategy_account_holding_charts import StrategyAccountHoldingCharts
        original=StrategyAccountHoldingCharts.bars
        for mode in ('account','target'):
            charts=self.charts(self.configuration)
            def changed(source, **kwargs):
                result=original(source, **kwargs)
                if mode=='account':
                    state=self.accounts.read()
                    self.accounts.append(dict(event_id='concurrent-cash',kind='CASH_CONFIRM',
                        amount='10',cash_basis='TOTAL_UNINVESTED'),expected_revision=state['revision'])
                else:
                    self.target(self.configuration,'concurrent-target')
                return result
            with self.subTest(mode=mode), patch.object(StrategyAccountHoldingCharts,'bars',changed):
                with self.assertRaisesRegex(ValueError,'STALE_REVISION' if mode=='account' else 'STALE_TARGET'):
                    self.bars(charts)

    def test_revision_required(self):
        charts=self.charts(self.configuration)
        with self.assertRaisesRegex(ValueError,'STALE_REVISION'):
            charts.bars(account_revision='0'*64,security_id='sid:AAA')


if __name__=='__main__':unittest.main()
