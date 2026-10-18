from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import sqlite3,unittest
from core.strategy_account_store import StrategyAccountStore


def event(identifier,amount='100'):
    return dict(event_id=identifier,kind='CASH_CONFIRM',amount=amount,cash_basis='TOTAL_UNINVESTED')


class StoreTests(unittest.TestCase):
    def test_absent_read_and_append_do_not_create(self):
        with TemporaryDirectory() as d:
            parent=Path(d)/'missing';store=StrategyAccountStore(parent/'strategy.sqlite3')
            self.assertIsNone(store.read());self.assertFalse(parent.exists())
            with self.assertRaisesRegex(ValueError,'ACCOUNT_NOT_INITIALIZED'):store.append(event('a'),expected_revision='x')
            self.assertFalse(parent.exists())

    def test_restart_replay_original_event_time_idempotency_and_tamper(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'account.sqlite3';now=datetime(2026,10,16,tzinfo=timezone.utc)
            store=StrategyAccountStore(p,clock=lambda:now);initial=store.initialize('one',operation_id='init')
            state,effect=store.append(event('cash'),expected_revision=initial['revision'])
            data=p.read_bytes()
            second=StrategyAccountStore(p,clock=lambda: (_ for _ in ()).throw(AssertionError('duplicate must not clock')))
            self.assertEqual(second.read(),state)
            self.assertEqual(second.append(event('cash'),expected_revision='obsolete'),(state,effect))
            self.assertEqual(p.read_bytes(),data)
            with self.assertRaisesRegex(ValueError,'EVENT_ID_CONFLICT'):second.append(event('cash','101'),expected_revision=state['revision'])
            with closing(sqlite3.connect(p)) as db:
                row=db.execute('SELECT payload,received_at FROM strategy_events').fetchone()
                self.assertIn('CASH_CONFIRM',row[0]);self.assertEqual(row[1],now.isoformat())
                db.execute("UPDATE strategy_events SET revision='tampered'");db.commit()
            with self.assertRaisesRegex(ValueError,'EVENT_REVISION_MISMATCH'):second.read()

    def test_concurrent_revision_only_one_event_commits(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'account.sqlite3';initial=StrategyAccountStore(p).initialize('one',operation_id='init');barrier=Barrier(2)
            def worker(identifier):
                store=StrategyAccountStore(p);barrier.wait()
                try:store.append(event(identifier),expected_revision=initial['revision']);return 'COMMITTED'
                except ValueError as e:return str(e)
            with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,['a','b']))
            self.assertCountEqual(results,['COMMITTED','STALE_REVISION'])
            self.assertEqual(len(StrategyAccountStore(p).read()['events']),1)

    def test_direct_fill_persists_and_requires_cash_reconfirmation(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'account.sqlite3';store=StrategyAccountStore(p,clock=lambda:datetime(2026,10,16,15,tzinfo=timezone.utc))
            initial=store.initialize('one',operation_id='init');confirmed,_=store.append(event('cash'),expected_revision=initial['revision'])
            fill=dict(event_id='direct',kind='DIRECT_FILL',security_id='A',side='BUY',quantity=2,price='10',fees='1',executed_at='2026-10-16T14:00:00Z')
            state,effect=store.append(fill,expected_revision=confirmed['revision'])
            self.assertEqual(effect['cash_delta'],'-21');self.assertEqual(state['cash'],'100')
            self.assertEqual(state['shares'],{'A':2});self.assertFalse(state['cash_confirmation_valid'])
            reopened=StrategyAccountStore(p);self.assertEqual(reopened.read(),state)
            self.assertEqual(reopened.append(fill,expected_revision='stale'),(state,effect))

    def test_future_fill_and_backdated_receipt_rejected(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'account.sqlite3'
            now=datetime(2026,10,16,13,tzinfo=timezone.utc)
            store=StrategyAccountStore(p,clock=lambda:now)
            initial=store.initialize('one',operation_id='init')
            confirmed,_=store.append(event('cash'),expected_revision=initial['revision'])
            fill=dict(event_id='direct',kind='DIRECT_FILL',security_id='A',side='BUY',quantity=2,price='10',fees='1',executed_at='2026-10-16T14:00:00Z')
            before=p.read_bytes()
            with self.assertRaisesRegex(ValueError,'FUTURE_EXECUTED_AT'):
                store.append(fill,expected_revision=confirmed['revision'])
            self.assertEqual(p.read_bytes(),before)
            self.assertEqual(store.read(),confirmed)
            now=datetime(2026,10,16,15,tzinfo=timezone.utc)
            store.append(fill,expected_revision=confirmed['revision'])
            with closing(sqlite3.connect(p)) as db:
                db.execute("UPDATE strategy_events SET received_at='2026-10-16T13:30:00+00:00' WHERE event_id='direct'")
                db.commit()
            with self.assertRaisesRegex(ValueError,'FUTURE_EXECUTED_AT'):store.read()

    def test_same_named_weak_schemas_are_rejected(self):
        variants=[
            'ordinal INTEGER PRIMARY KEY,event_id TEXT NOT NULL,payload TEXT NOT NULL,received_at TEXT NOT NULL,revision TEXT NOT NULL',
            'ordinal INTEGER PRIMARY KEY,event_id TEXT UNIQUE,payload TEXT NOT NULL,received_at TEXT NOT NULL,revision TEXT NOT NULL',
            'ordinal INTEGER PRIMARY KEY,event_id TEXT NOT NULL UNIQUE,payload BLOB NOT NULL,received_at TEXT NOT NULL,revision TEXT NOT NULL',
            'ordinal INTEGER NOT NULL,event_id TEXT NOT NULL UNIQUE,payload TEXT NOT NULL,received_at TEXT NOT NULL,revision TEXT NOT NULL',
        ]
        for columns in variants:
            with self.subTest(columns=columns),TemporaryDirectory() as d:
                p=Path(d)/'account.sqlite3';store=StrategyAccountStore(p)
                store.initialize('one',operation_id='init')
                with closing(sqlite3.connect(p)) as db:
                    db.execute('DROP TABLE strategy_events')
                    db.execute('CREATE TABLE strategy_events('+columns+')');db.commit()
                before=p.read_bytes()
                with self.assertRaisesRegex(ValueError,'FOREIGN_DATABASE_SCHEMA'):store.read()
                with self.assertRaisesRegex(ValueError,'FOREIGN_DATABASE_SCHEMA'):store.append(event('x'),expected_revision='x')
                self.assertEqual(p.read_bytes(),before)

    def test_foreign_schema_and_bad_clock_do_not_modify(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'foreign.sqlite3'
            with closing(sqlite3.connect(p)) as db:db.execute('CREATE TABLE paper_accounts(id TEXT)');db.commit()
            before=p.read_bytes();store=StrategyAccountStore(p)
            for operation in [store.read,lambda:store.initialize('a',operation_id='init'),lambda:store.append(event('a'),expected_revision='x')]:
                with self.assertRaisesRegex(ValueError,'FOREIGN_DATABASE_SCHEMA'):operation()
                self.assertEqual(p.read_bytes(),before)
            p=Path(d)/'strategy.sqlite3';store=StrategyAccountStore(p,clock=lambda:datetime(2026,10,16));initial=store.initialize('a',operation_id='init')
            before=p.read_bytes()
            with self.assertRaisesRegex(ValueError,'AWARE_SERVER_CLOCK_REQUIRED'):store.append(event('a'),expected_revision=initial['revision'])
            self.assertEqual(store.read(),initial);self.assertEqual(p.read_bytes(),before)


if __name__=='__main__':unittest.main()
