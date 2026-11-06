import unittest,json
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime,timezone
from hashlib import sha256
from core.strategy_account_store import StrategyAccountStore
from data.roa_execution_lifecycle import RoaExecutionLifecycle,digest
from data.roa_close_recovery import TrustedCloseRecovery

class SqliteRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)
        self.now=datetime(2026,11,6,21,5,tzinfo=timezone.utc)
        self.store=StrategyAccountStore(self.root/'account.db',clock=lambda:self.now)
        self.store.initialize('A',operation_id='init')
        self.append(dict(event_id='cash',kind='CASH_CONFIRM',amount='10000',cash_basis='TOTAL_UNINVESTED'))
        self.life=RoaExecutionLifecycle(path=self.root/'life.json',account_id='A',strategy_epoch='E',contract_sha256='a'*64)
        state=self.life.plan(signal=dict(signal_date='2026-11-05',decision_date='2026-10-30',risk_on=True,weights={'X':'1/10'},signal_id='b'*64),session='2026-11-06',open_at='2026-11-06T14:30:00Z',open_until='2026-11-06T14:35:00Z',close_at='2026-11-06T20:55:00Z',close_until='2026-11-06T21:00:00Z')
        self.life.materialize_open(event_id=state['events'][0]['event_id'],account=self.store.read(),opening_prices={'X':'100'},now='2026-11-06T14:30:00Z')
        self.raw=self.root/'close.json';self.raw.write_text(json.dumps({'X':'75'}))
        self.hook=lambda:None
        self.recovery=TrustedCloseRecovery(account_store=self.store,lifecycle=self.life,directory=self.root/'checkpoints',evidence_root=self.root,calendar=lambda d:dict(close_at=d+'T21:00:00Z',previous_session='2026-11-05'),calendar_sessions=['2026-11-05','2026-11-06'],price_reader=self.capture,clock=lambda:self.now)
    def tearDown(self):self.temp.cleanup()
    def append(self,event):return self.store.append(event,expected_revision=self.store.read()['revision'])
    def capture(self,day,shares):
        self.hook()
        return dict(prices={'X':'75'},source_hashes={'close.json':sha256(self.raw.read_bytes()).hexdigest()})
    def late_buy(self):
        self.now=datetime(2026,11,6,21,10,tzinfo=timezone.utc)
        self.append(dict(event_id='buy',kind='DIRECT_FILL',security_id='X',side='BUY',quantity=9,price='100',fees='0',executed_at='2026-11-06T14:31:00Z'))
    def test_same_day_late_fill_recovers_and_retry_is_idempotent(self):
        self.recovery.observe('2026-11-06')
        self.assertEqual(self.life.read()['peaks'],{})
        self.late_buy();before=self.store.read()
        result=self.recovery.observe('2026-11-06')
        self.assertEqual(result['state']['pending'],['X'])
        self.assertEqual(result['state']['peaks'],{'X':'100'})
        self.assertEqual(self.store.read(),before)
        self.assertFalse(before['cash_confirmation_valid'])
        version=self.life.read()['version']
        self.assertEqual(self.recovery.observe('2026-11-06')['status'],'UNCHANGED')
        self.assertEqual(self.life.read()['version'],version)
    def test_concurrent_cash_write_blocks_apply(self):
        self.recovery.observe('2026-11-06');self.late_buy();before=digest(self.life.read())
        self.hook=lambda:self.append(dict(event_id='newcash',kind='CASH_CONFIRM',amount='9000',cash_basis='TOTAL_UNINVESTED'))
        with self.assertRaisesRegex(ValueError,'ACCOUNT_CHANGED'):self.recovery.observe('2026-11-06')
        self.assertEqual(digest(self.life.read()),before)
        self.assertEqual(self.store.read()['cash'],'9000')
    def test_checkpoint_tampering_rejected(self):
        self.recovery.observe('2026-11-06');self.late_buy()
        path=self.root/'checkpoints/2026-11-06.checkpoint.json';data=json.loads(path.read_text());data['document']['checkpoint']['peaks']={'X':'1000'};path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'CHECKPOINT_HASH'):self.recovery.observe('2026-11-06')

    def test_apply_holds_real_sqlite_write_reservation(self):
        import sqlite3
        original=self.life._save;blocked=[]
        def save(state):
            other=sqlite3.connect(str(self.store.path),timeout=0.01,isolation_level=None)
            try:
                with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
                    other.execute('BEGIN IMMEDIATE')
                blocked.append(True)
            finally:other.close()
            return original(state)
        self.life._save=save
        self.recovery.observe('2026-11-06')
        self.assertEqual(blocked,[True])

    def test_cash_only_close_uses_calendar_evidence_then_real_entry(self):
        calendar_file=self.root/'calendar.json'
        calendar_file.write_text(json.dumps({'sessions':['2026-11-05','2026-11-06','2026-11-09']}))
        calendar_pin={'calendar.json':sha256(calendar_file.read_bytes()).hexdigest()}
        observed=[]
        def capture(day,shares):
            observed.append((day,dict(shares)))
            return dict(prices={'X':'75'} if shares else {},source_hashes=({'close.json':sha256(self.raw.read_bytes()).hexdigest()} if shares else calendar_pin))
        self.recovery.price_reader=capture
        self.recovery.sessions=['2026-11-05','2026-11-06','2026-11-09']
        self.recovery.calendar=lambda d:dict(close_at=d+'T21:00:00Z',previous_session='2026-11-06' if d=='2026-11-09' else '2026-11-05')
        self.recovery.observe('2026-11-06')
        self.assertEqual(self.life.read()['close_shares'],{})
        self.now=datetime(2026,11,9,21,5,tzinfo=timezone.utc)
        self.append(dict(event_id='buy-later',kind='DIRECT_FILL',security_id='X',side='BUY',quantity=9,price='75',fees='0',executed_at='2026-11-09T14:31:00Z'))
        result=self.recovery.observe('2026-11-09')
        self.assertEqual(result['state']['close_shares'],{'X':9})
        self.assertEqual(observed,[('2026-11-06',{}),('2026-11-09',{'X':9})])

    def test_later_open_and_later_fill_do_not_replay_unchanged_old_close(self):
        self.recovery.observe('2026-11-06')
        self.now=datetime(2026,11,9,15,tzinfo=timezone.utc)
        state=self.life.read();event=dict(state['events'][0]);event.update(event_id='new-open',session='2026-11-09',materialized_revision='new-revision');state['events'].append(event);self.life._save(state)
        self.append(dict(event_id='today-buy',kind='DIRECT_FILL',security_id='X',side='BUY',quantity=9,price='100',fees='0',executed_at='2026-11-09T14:31:00Z'))
        before=digest(self.life.read())
        result=self.recovery.observe('2026-11-06')
        self.assertEqual(result['status'],'UNCHANGED_CLOSE_HOLDINGS')
        self.assertEqual(digest(self.life.read()),before)

if __name__=='__main__':unittest.main()
