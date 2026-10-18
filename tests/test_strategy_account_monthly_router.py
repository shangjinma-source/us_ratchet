"""Dispatch tests with real build_runtime, monthly services and SQLite stores.

Only selection/evidence generation is synthetic; no vendor requests or research.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from data.strategy_account_runtime import ACCOUNT_ID, build_runtime
from data.strategy_account_monthly_router import MonthlyRuntimeRouter
import test_strategy_account_monthly_release as release_fixture


class MonthlyRouterTests(unittest.TestCase):
    def setUp(self):
        self.fixture = release_fixture.MonthlyReleaseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.now = datetime.fromisoformat('2026-12-01T15:00:00+00:00')
        self.configuration = self.fixture.resolve()
        self.selection_calls = 0
        self.executed_configurations = []
        self.built = []
        self.archive = dict(schema='REAL_STRATEGY_RUNTIME_ARCHIVE_V1', entries=[])
        self.add_archive('runtime.json',self.configuration)
        self.router = self.make_router()
        self.router.accounts.initialize(ACCOUNT_ID,operation_id='init')
        self.append(dict(event_id='cash',kind='CASH_CONFIRM',amount='2000',cash_basis='TOTAL_UNINVESTED'))

    def add_archive(self,path,configuration):
        digest = self.fixture.put(path,configuration)
        self.archive['entries'].append(dict(configuration_path=path,configuration_sha256=digest))

    def make_router(self, identity_configuration=None, migration_control=None):
        return MonthlyRuntimeRouter(root=self.root, registry_path='registry.json',
            registry_sha256=self.fixture.put('registry.json',self.fixture.registry),
            archive_path='archive.json',archive_sha256=self.fixture.put('archive.json',self.archive),
            clock=lambda:self.now,runtime_builder=self.build,identity_configuration=identity_configuration,migration_control=migration_control)

    def build(self,**kwargs):
        # Production constructor and pin checks are real. Avoid market/search IO only.
        runtime = build_runtime(**kwargs)
        configuration = kwargs['configuration']
        sid = self.fixture.identity['candidates'][0]['security_id']
        ticker = self.fixture.identity['candidates'][0]['ticker']
        def select():
            self.selection_calls += 1
            state = runtime.accounts.read()
            binding = dict(account_id=state['account_id'],account_revision=state['revision'],
                search_arguments={'metadata':{sid:{'ticker':ticker}}},
                training_cutoff_date=configuration['training_closed_at'][:10],
                valuation_at=self.now.isoformat(),strategy_equity='2000',
                documents={'training_manifest':configuration['training_manifest']},
                source_hashes={configuration['training_manifest']:configuration['training_sha256'],
                    configuration['identity_manifest']:configuration['identity_sha256']})
            payload = dict(input_binding=binding,input_id=sha256(canonical(binding)).hexdigest(),
                           target_quantities={sid:1})
            decision = dict(payload=payload,decision_id=sha256(canonical(payload)).hexdigest())
            runtime.selection.current = (decision,None,state)
            return dict(status='READY')
        def evidence(state,target,now):
            self.executed_configurations.append(deepcopy(configuration))
            return dict(marks={sid:dict(security_id=sid,currency='USD',price_basis='CURRENT_UNIT',
                observed_at=now.isoformat(),price='100')},limits={sid:dict(security_id=sid,
                ticker=ticker,price_basis='CURRENT_UNIT',observed_at=now.isoformat(),buy='99',sell='100',
                buy_reason='synthetic',sell_reason='synthetic',buy_evaluated=True,
                reference_valid_until=(now+timedelta(seconds=90)).isoformat())})
        runtime.selection.select = select
        runtime.execution_provider = evidence
        self.built.append(runtime)
        return runtime

    def append(self,event):
        self.router.accounts.append(event,expected_revision=self.router.accounts.read()['revision'])

    def request(self,event_id='target',reason='INITIAL'):
        prior = self.router.current()
        return dict(event_id=event_id,reason=reason,expected_revision=self.router.accounts.read()['revision'],
                    previous_target_id=prior['target_id'] if prior else None)

    def test_generation_preview_share_real_stores_and_lock(self):
        before = self.router.accounts.read()
        target = self.router.generate(**self.request())
        self.assertEqual(self.router.preview()['target_id'],target['target_id'])
        self.assertEqual(self.selection_calls,1)
        self.assertEqual(self.router.accounts.read(),before)
        runtime = self.built[0]
        self.assertIs(runtime.accounts,self.router.accounts)
        self.assertIs(runtime.selection.store,self.router.accounts)
        self.assertIs(runtime.targets,self.router.targets)
        self.assertIs(runtime.lock,self.router.lock)
        self.assertIs(runtime.selection.lock,self.router.lock)
        self.assertFalse(hasattr(self.router,'selection'))
        self.router.validate_current_target_pins()

    def test_cross_month_read_and_idempotency_survive_missing_publication(self):
        request = self.request()
        target = self.router.generate(**request)
        self.now = datetime.fromisoformat('2027-01-04T15:00:00+00:00')
        self.assertEqual(self.router.current(),target)
        self.assertEqual(self.router.generate(**request),target)
        with self.assertRaisesRegex(ValueError,'CURRENT_MONTH_RELEASE_REQUIRED'):
            self.router.generate(**self.request('next','MONTHLY_SELECTION'))
        with self.assertRaisesRegex(ValueError,'MONTHLY_TARGET_REQUIRED'):
            self.router.preview()
        self.assertEqual(self.selection_calls,1)
        self.assertEqual(self.router.current(),target)

    def test_same_month_other_configuration_cannot_replace_preview(self):
        target = self.router.generate(**self.request())
        new = dict(self.configuration,training_manifest='new-training.json',training_sha256='9'*64)
        self.add_archive('new-runtime.json',new)
        # Current publication is deliberately unavailable: preview must not consult it.
        restarted = self.make_router()
        restarted.registry_sha256 = '0'*64
        self.assertEqual(restarted.preview()['target_id'],target['target_id'])
        self.assertEqual(self.executed_configurations[-1],self.configuration)
        self.assertEqual(self.selection_calls,1)

    def test_identity_coverage_rejects_before_build_or_search(self):
        self.append(self.fixture.holding_event())
        self.append(dict(event_id='new-cash',kind='CASH_CONFIRM',amount='1980',cash_basis='TOTAL_UNINVESTED'))
        with self.assertRaisesRegex(ValueError,'IDENTITY_NOT_UNIQUE_OR_UNAVAILABLE'):
            self.router.generate(**self.request())
        self.assertEqual(self.built,[])
        self.assertEqual(self.selection_calls,0)
        self.assertIsNone(self.router.current())

    def test_concurrent_generation_has_one_publication_and_cas_failure(self):
        request = self.request()
        def run(event_id):
            try:return self.router.generate(**dict(request,event_id=event_id))
            except ValueError as error:return str(error)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(run,['first','second']))
        self.assertEqual(sum(isinstance(value,dict) for value in results),1)
        self.assertIn('STALE_TARGET',results)
        self.assertEqual(self.selection_calls,1)
        self.assertEqual(len(self.router.targets.history()),1)

    def migration(self, configuration=None):
        configuration = configuration or self.configuration
        return dict(purpose='MIGRATION_CONTROL',target_month=configuration['target_month'],
                    configuration=configuration,allowed_reasons=['INITIAL','EXPLICIT_RECONFIGURE'])

    def test_migration_initial_adoption_is_explicit_and_does_not_need_monthly_release(self):
        initial = dict(self.configuration,training_closed_at='2026-12-01T14:00:00+00:00')
        self.archive['entries']=[];self.add_archive('initial.json',initial)
        control = self.migration(initial)
        router = self.make_router(migration_control=control)
        control['configuration'] = {}
        router.registry_sha256 = '0'*64
        target = router.generate(**self.request())
        self.assertEqual(target['payload']['target_month'],'2026-12')
        request = dict(event_id='again',reason='EXPLICIT_RECONFIGURE',
            expected_revision=router.accounts.read()['revision'],previous_target_id=target['target_id'])
        self.assertEqual(router.generate(**request)['payload']['previous_target_id'],target['target_id'])
        self.now = datetime.fromisoformat('2027-01-04T15:00:00+00:00')
        self.assertEqual(router.generate(**request)['payload']['request'],request)
        with self.assertRaisesRegex(ValueError,'REGISTRY_SOURCE_CHANGED'):
            router.generate(event_id='new-month',reason='MONTHLY_SELECTION',
                expected_revision=router.accounts.read()['revision'],previous_target_id=router.current()['target_id'])

    def test_expired_migration_uses_current_publication_not_old_configuration(self):
        old = dict(self.configuration,target_month='2026-11')
        router = self.make_router(migration_control=self.migration(old))
        result = router.generate(**self.request())
        self.assertEqual(result['payload']['target_month'],'2026-12')
        self.assertEqual(self.selection_calls,1)

    def test_migration_does_not_cover_monthly_selection_or_invalid_archive(self):
        router = self.make_router(migration_control=self.migration())
        router.registry_sha256='0'*64
        with self.assertRaisesRegex(ValueError,'REGISTRY_SOURCE_CHANGED'):
            router.generate(**dict(self.request(),reason='MONTHLY_SELECTION'))
        bad = dict(self.configuration,training_sha256='0'*64)
        router = self.make_router(migration_control=self.migration(bad))
        with self.assertRaisesRegex(ValueError,'RELEASE_RUNTIME_ARCHIVE_NOT_UNIQUE_OR_UNAVAILABLE'):
            router.generate(**self.request())
        self.assertEqual(self.selection_calls,0)
        self.assertIsNone(router.current())

    def test_migration_schema_and_future_training_refused(self):
        for field,value in [('purpose','USER_PREFERENCE'),('allowed_reasons',['INITIAL','MONTHLY_SELECTION']),
                            ('target_month','2026-13')]:
            control=self.migration();control[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.make_router(migration_control=control)
        future=dict(self.configuration,training_closed_at='2026-12-02T15:00:00+00:00')
        self.archive['entries']=[];self.add_archive('future.json',future)
        router=self.make_router(migration_control=self.migration(future))
        with self.assertRaisesRegex(ValueError,'MIGRATION_TRAINING_NOT_CLOSED'):
            router.generate(**self.request())
        self.assertEqual(self.selection_calls,0)

    def test_initial_valuation_uses_migration_only_not_identity_bootstrap(self):
        router=self.make_router(migration_control=self.migration())
        router.registry_sha256='0'*64
        runtime=router._runtime(self.configuration)
        seen=[]
        runtime.valuation=lambda state: seen.append(state['revision']) or {}
        self.assertEqual(router.valuation(router.accounts.read()),{})
        self.assertEqual(len(seen),1)
        self.assertIsNone(router.current())
        self.assertEqual(self.selection_calls,0)

    def test_bootstrap_identity_allows_record_lookup_without_current_month_release(self):
        router = self.make_router(identity_configuration=self.configuration)
        self.now = datetime.fromisoformat('2027-01-04T15:00:00+00:00')
        before = router.accounts.read()
        row = self.fixture.identity['candidates'][0]
        result = router.resolve_identity(row['ticker'])
        self.assertEqual(result['security_id'],row['security_id'])
        self.assertEqual(router.accounts.read(),before)
        with self.assertRaisesRegex(ValueError,'CURRENT_MONTH_RELEASE_REQUIRED'):
            router.generate(**self.request())
        self.assertIsNone(router.current())
        self.assertEqual(self.selection_calls,0)

    def test_unarchived_bootstrap_identity_configuration_is_refused(self):
        configuration = dict(self.configuration,training_sha256='9'*64)
        router = self.make_router(identity_configuration=configuration)
        self.now = datetime.fromisoformat('2027-01-04T15:00:00+00:00')
        with self.assertRaisesRegex(ValueError,'RELEASE_RUNTIME_ARCHIVE_NOT_UNIQUE_OR_UNAVAILABLE'):
            router.resolve_identity(self.fixture.identity['candidates'][0]['ticker'])
        self.assertEqual(self.built,[])
        self.assertIsNone(router.current())

    def test_identity_without_target_uses_reviewed_material_without_account_write(self):
        before = self.router.accounts.read()
        row = self.fixture.identity['candidates'][0]
        result = self.router.resolve_identity(row['ticker'])
        self.assertEqual(result['security_id'],row['security_id'])
        self.assertEqual(result['source_hashes'][self.configuration['identity_manifest']],
                         self.configuration['identity_sha256'])
        self.assertEqual(self.router.accounts.read(),before)
        self.assertIsNone(self.router.current())
        self.assertEqual(self.selection_calls,0)

    def test_identity_preserves_departed_holding_and_rejects_unknown_ticker(self):
        self.fixture.add_departed_identity()
        self.configuration = self.fixture.resolve()
        self.archive['entries'] = []
        self.add_archive('runtime.json',self.configuration)
        self.router = self.make_router()
        self.router.generate(**self.request())
        self.append(self.fixture.holding_event())
        before = self.router.accounts.read()
        result = self.router.resolve_identity('DEPARTED')
        self.assertEqual(result['security_id'],'departed-id')
        with self.assertRaisesRegex(ValueError,'IDENTITY_NOT_UNIQUE_OR_UNAVAILABLE'):
            self.router.resolve_identity('UNKNOWN')
        self.assertEqual(self.router.accounts.read(),before)
        self.assertEqual(self.selection_calls,1)

    def test_identity_with_target_ignores_new_publication_and_detects_source_drift(self):
        self.router.generate(**self.request())
        before = self.router.accounts.read()
        row = self.fixture.identity['candidates'][0]
        self.router.registry_sha256 = '0'*64
        result = self.router.resolve_identity(row['ticker'])
        self.assertEqual(result['security_id'],row['security_id'])
        self.assertEqual(self.router.accounts.read(),before)
        (self.root/'synthetic-evidence.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'IDENTITY_SOURCE_CHANGED'):
            self.router.resolve_identity(row['ticker'])
        self.assertEqual(self.router.accounts.read(),before)
        self.assertEqual(self.selection_calls,1)

    def test_cached_runtime_rechecks_nonminimum_executing_source_before_quotes(self):
        from data.strategy_account_target_service import MINIMUM_RUNTIME_PATHS
        path = 'data/strategy_account_market_capture.py'
        self.assertNotIn(path,MINIMUM_RUNTIME_PATHS)
        self.router.generate(**self.request())
        self.assertEqual(len(self.built),1)
        executing_path = Path(__file__).resolve().parents[1]/path
        original_read = Path.read_bytes
        def read(instance):
            if instance.resolve() == executing_path:
                return b'changed executing source'
            return original_read(instance)
        with patch.object(Path,'read_bytes',read):
            with self.assertRaisesRegex(ValueError,'EXECUTING_COMPOSITION_SOURCE_CHANGED'):
                self.router.preview()
        self.assertEqual(self.executed_configurations,[])
        self.assertEqual(len(self.built),1)

    def test_unarchived_publication_rejected_before_build_or_selection(self):
        self.archive['entries'] = []
        self.router.archive_sha256 = self.fixture.put('archive.json',self.archive)
        before = self.router.accounts.read()
        with self.assertRaisesRegex(ValueError,'RELEASE_RUNTIME_ARCHIVE_NOT_UNIQUE_OR_UNAVAILABLE'):
            self.router.generate(**self.request())
        self.assertEqual(self.selection_calls,0)
        self.assertEqual(self.built,[])
        self.assertIsNone(self.router.current())
        self.assertFalse(self.router.targets.path.exists())
        self.assertEqual(self.router.accounts.read(),before)

    def test_duplicate_event_conflict_and_source_drift(self):
        request = self.request()
        self.router.generate(**request)
        with self.assertRaisesRegex(ValueError,'TARGET_EVENT_CONFLICT'):
            self.router.generate(**dict(request,expected_revision='0'*64))
        (self.root/'runtime.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'REGISTRY_SOURCE_CHANGED'):
            self.router.preview()
        self.assertEqual(len(self.router.targets.history()),1)


if __name__ == '__main__':
    unittest.main()
