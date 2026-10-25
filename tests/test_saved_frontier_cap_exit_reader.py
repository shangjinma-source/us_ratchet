"""Source-backed isolated risk tests; no optimizer, live account or fake signal."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.saved_frontier_cap_exit_reader import (
    POLICY_ID, clone_monthly_risk_store, project_saved_frontier_cap_exit,
)
from data.strategy_daily_target_gate import resolve_daily_target
from test_saved_frontier_daily_evidence import joint_fixture


def digest(raw):
    return sha256(raw).hexdigest()


class SavedFrontierCapExitReaderTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory(prefix='frontier-risk-test-', dir=Path(__file__).resolve().parents[1] / 'tmp')
        self.case = joint_fixture(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def clone(self, name='inherited.sqlite3', source=None):
        c = self.case
        source = source or c['risk_path']
        return Path(clone_monthly_risk_store(research_root=c['research_root'], source_path=source,
            source_sha256=digest(source.read_bytes()), clone_name=name)['path'])

    def arguments(self, path):
        c = self.case
        return dict(research_root=c['research_root'], risk_path=path, target_id=c['target']['target_id'],
            state=c['state'], review_bytes=c['review_bytes'], trusted_review_sha256=c['trusted_review_sha256'],
            files=c['files'], now=c['now'], enabled=True)

    def test_all_three_tables_inherited_expanded_exit_preserved_and_real_archive(self):
        c = self.case
        originals = (deepcopy(c['state']), deepcopy(c['target']), deepcopy(c['proposal']),
                     c['accounts'].path.read_bytes(), c['risk_path'].read_bytes())
        path = self.clone()
        self.assertEqual(path.read_bytes(), c['risk_path'].read_bytes())
        result = project_saved_frontier_cap_exit(**self.arguments(path))
        self.assertEqual(result['baseline_targets'], {'A':99, 'B':99, 'D':0, 'E':0})
        self.assertEqual(result['signal']['effective_target_quantities'], {'A':0, 'B':99, 'D':0, 'E':0})
        self.assertEqual(result['signal']['policy_id'], POLICY_ID)
        self.assertEqual(result['signal']['target_id'], c['target']['target_id'])
        self.assertEqual(result['signal']['proposal_id'], c['proposal']['proposal_id'])
        self.assertEqual(result['projection']['state']['exited'], ['A'])
        self.assertEqual(result['projection']['state']['decision_date'], '2026-10-20')
        self.assertEqual(result['projection']['state']['session_date'], '2026-10-22')
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM risk_prices').fetchone()[0], 12)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM risk_domain_evidence').fetchone()[0], 5)
        archive = result['evidence_archive']
        receipt_bytes = Path(archive['receipt_path']).read_bytes()
        self.assertEqual(digest(receipt_bytes), archive['receipt_sha256'])
        receipt = json.loads(receipt_bytes)
        self.assertTrue(Path(archive['complete_path']).is_file())
        for source, expected in receipt['source_sha256'].items():
            raw = (Path(archive['receipt_path']).parent / 'sources' / (expected + '.bin')).read_bytes()
            self.assertEqual(digest(raw), expected, source)
        self.assertEqual((c['state'], c['target'], c['proposal'], c['accounts'].path.read_bytes(), c['risk_path'].read_bytes()), originals)
        gate = resolve_daily_target(account_id=c['state']['account_id'], account_revision=c['state']['revision'],
            target_id=c['target']['target_id'], target_month='2026-10', monthly_quantities=result['baseline_targets'],
            strategy_shares=c['state']['shares'], available_cash=c['state']['available_cash'],
            pending_orders=[o for o in c['state']['orders'].values() if o['status']=='OPEN'], now=c['now'],
            expected_policy_id=POLICY_ID, signal=result['signal'])
        self.assertEqual(gate['status'], 'DAILY_TARGET_READY')
        self.assertEqual(next(row for row in gate['rows'] if row['security_id']=='E')['action'], 'WAIT')

    def test_same_seed_repeat_is_identical_and_stale_review_is_rejected(self):
        first_path = self.clone('first.sqlite3')
        second_path = self.clone('second.sqlite3')
        first = project_saved_frontier_cap_exit(**self.arguments(first_path))
        second = project_saved_frontier_cap_exit(**self.arguments(second_path))
        self.assertEqual(first['projection'], second['projection'])
        # Archive IDs include the actual clone path and are deliberately distinct.
        self.assertNotEqual(first['evidence_archive']['receipt_sha256'], second['evidence_archive']['receipt_sha256'])
        before = first_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'FRONTIER_REVIEW_BINDING'):
            project_saved_frontier_cap_exit(**self.arguments(first_path))
        self.assertEqual(first_path.read_bytes(), before)

    def test_missing_source_and_same_month_reset_rejected_without_risk_write(self):
        path = self.clone()
        before = path.read_bytes()
        arguments = self.arguments(path)
        arguments['files'] = dict(arguments['files'])
        del arguments['files']['raw/B.json']
        with self.assertRaisesRegex(ValueError, 'FRONTIER_SOURCE_DOMAIN'):
            project_saved_frontier_cap_exit(**arguments)
        with self.assertRaisesRegex(ValueError, 'FRONTIER_SAME_MONTH_RESET_FORBIDDEN'):
            project_saved_frontier_cap_exit(**dict(self.arguments(path), authorized_monthly_reset='2026-10-20'))
        self.assertEqual(path.read_bytes(), before)

    def test_fully_sold_ledger_zero_key_does_not_require_new_price_history(self):
        c = self.case
        event = deepcopy(next(row['payload'] for row in c['state']['events']
                              if row['payload'].get('kind') == 'DIRECT_FILL'))
        event.update(event_id='sold-old-D', side='SELL', executed_at='2026-10-22T14:00:00+00:00')
        c['accounts'].clock = lambda: datetime.fromisoformat('2026-10-22T15:00:00+00:00')
        c['accounts'].append(event, expected_revision=c['accounts'].read()['revision'])
        c['state'] = c['accounts'].read()
        self.assertEqual(c['state']['shares']['D'], 0)
        files = deepcopy(c['files'])
        review = json.loads(c['review_bytes'])
        identity = json.loads(files['identities.json'])
        identity['securities'].pop('D')
        files['identities.json'] = canonical(identity)
        inputs = json.loads(files['normalized.json'])
        inputs['histories'].pop('D')
        for name in ('quantities', 'price_units'): inputs['base_target'][name].pop('D')
        files['normalized.json'] = canonical(inputs)
        for name in ('raw_by_security', 'unit_reviews'):
            files.pop(review['documents'][name].pop('D'))
        for name in review['documents']['unit_reviews'].values():
            unit = json.loads(files[name]); unit['identity_sha256'] = digest(files['identities.json'])
            files[name] = canonical(unit)
        review.update(account_revision=c['state']['revision'],
                      source_sha256={name:digest(raw) for name,raw in files.items()})
        c.update(files=files, review_bytes=canonical(review), trusted_review_sha256=digest(canonical(review)))
        output = project_saved_frontier_cap_exit(**self.arguments(self.clone()))
        self.assertEqual(output['zero_balance_security_ids'], ['D'])
        self.assertNotIn('D', output['source_admission']['required_security_ids'])
        self.assertNotIn('D', output['risk_baseline_targets'])
        self.assertEqual(output['baseline_targets']['D'], 0)
        self.assertEqual(output['signal']['effective_target_quantities']['D'], 0)
        gate = resolve_daily_target(account_id=c['state']['account_id'], account_revision=c['state']['revision'],
            target_id=c['target']['target_id'], target_month='2026-10', monthly_quantities=output['baseline_targets'],
            strategy_shares=c['state']['shares'], available_cash=c['state']['available_cash'],
            pending_orders=[o for o in c['state']['orders'].values() if o['status']=='OPEN'], now=c['now'],
            expected_policy_id=POLICY_ID, signal=output['signal'])
        self.assertEqual(gate['status'], 'DAILY_TARGET_READY')

    def test_missing_recorded_old_history_and_price_tamper_reject_transactionally(self):
        for name, sql in [('missing.sqlite3', "DELETE FROM risk_prices WHERE session_date='2026-10-20'"),
                          ('changed.sqlite3', "UPDATE risk_prices SET close='101' WHERE session_date='2026-10-20'")]:
            path = self.clone(name)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute(sql)
                connection.commit()
            before = path.read_bytes()
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'RISK_OLD_DOMAIN_HISTORY_UNVERIFIED|RISK_RECORDED_PRICE_CHANGED'):
                project_saved_frontier_cap_exit(**self.arguments(path))
            self.assertEqual(path.read_bytes(), before)

    def test_new_month_requires_authorization_then_resets_old_exit(self):
        c = self.case
        seed = Path(self.folder.name) / 'prior-month.sqlite3'
        store = MonthlyPeakExitStore(seed)
        observations = []
        for day, price in [('2026-09-28', '100'), ('2026-09-29', '70')]:
            row = dict(decision_date='2026-09-28', session_date=day, closes={'A':price}, unit_ids={'A':'unit-A'})
            observations.append(dict(row, evidence_sha256=digest(json.dumps(row, sort_keys=True).encode())))
        store.advance(account_id=c['state']['account_id'], expected_previous_session=None,
            observations=observations, baseline_targets={'A':100}, target_month='2026-09')
        path = self.clone(source=seed)
        files = deepcopy(c['files'])
        raw = json.loads(files['raw/A.json'])
        raw['chart']['result'][0]['indicators']['quote'][0]['close'] = [100,101,102]
        raw['chart']['result'][0]['indicators']['adjclose'][0]['adjclose'] = [100,101,102]
        files['raw/A.json'] = canonical(raw)
        unit = json.loads(files['units/A.json']); unit['raw_sha256'] = digest(files['raw/A.json'])
        files['units/A.json'] = canonical(unit)
        inputs = json.loads(files['normalized.json'])
        inputs['histories']['A']['source_reference'] = 'sha256:' + digest(files['raw/A.json'])
        for row, price in zip(inputs['histories']['A']['closes'], [100,101,102]): row['close'] = str(price)
        files['normalized.json'] = canonical(inputs)
        review = json.loads(c['review_bytes'])
        review['risk_state_sha256'] = digest(canonical(store.read(c['state']['account_id'])))
        review['source_sha256'] = {name:digest(body) for name,body in files.items()}
        review_bytes = canonical(review)
        arguments = dict(self.arguments(path), files=files, review_bytes=review_bytes,
                         trusted_review_sha256=digest(review_bytes))
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'FRONTIER_NEW_MONTH_AUTHORIZATION_REQUIRED'):
            project_saved_frontier_cap_exit(**arguments)
        self.assertEqual(path.read_bytes(), before)
        result = project_saved_frontier_cap_exit(**dict(arguments, authorized_monthly_reset='2026-10-20'))
        self.assertEqual(result['projection']['state']['target_month'], '2026-10')
        self.assertEqual(result['projection']['state']['decision_date'], '2026-10-20')
        self.assertEqual(result['signal']['effective_target_quantities']['A'], 99)
        self.assertEqual(result['projection']['state']['exited'], [])
        self.assertEqual(store.read(c['state']['account_id'])['exited'], ['A'])

    def test_clone_rejects_missing_tables_bad_hash_path_and_overwrite(self):
        c = self.case
        arguments = dict(research_root=c['research_root'], source_path=c['risk_path'],
                         source_sha256=digest(c['risk_path'].read_bytes()), clone_name='copy.sqlite3')
        with self.assertRaisesRegex(ValueError, 'FRONTIER_RISK_SOURCE_HASH'):
            clone_monthly_risk_store(**dict(arguments, source_sha256='f'*64))
        with self.assertRaisesRegex(ValueError, 'FRONTIER_RISK_CLONE_NAME'):
            clone_monthly_risk_store(**dict(arguments, clone_name='../escape.sqlite3'))
        clone_monthly_risk_store(**arguments)
        with self.assertRaisesRegex(ValueError, 'FRONTIER_RISK_CLONE_CREATE_ONLY'):
            clone_monthly_risk_store(**arguments)
        broken = Path(self.folder.name) / 'state-only.sqlite3'
        with closing(sqlite3.connect(broken)) as connection:
            connection.execute('CREATE TABLE risk_state(account_id TEXT,state TEXT)')
        with self.assertRaisesRegex(ValueError, 'FRONTIER_RISK_ALL_THREE_TABLES_REQUIRED'):
            clone_monthly_risk_store(**dict(arguments, source_path=broken, source_sha256=digest(broken.read_bytes()),
                                          clone_name='broken.sqlite3'))

    def test_disabled_projection_does_no_io(self):
        output = project_saved_frontier_cap_exit(research_root=None, risk_path=None, target_id=None,
            state=None, review_bytes=None, trusted_review_sha256=None, files=None, now=None)
        self.assertEqual(output['status'], 'SAVED_FRONTIER_RISK_DISABLED')


if __name__ == '__main__':
    unittest.main()
