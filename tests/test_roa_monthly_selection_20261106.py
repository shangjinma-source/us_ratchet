import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from data.roa_monthly_selection import generate_month_selection,RoaMonthlySelectionLoader
from data.roa_execution_lifecycle import RoaExecutionLifecycle

ROOT=Path(__file__).resolve().parents[1]
MANIFEST='tmp/monthly_recovery_20261103/training_scoped_publication/manifest.json'


class MonthlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions=[r['date'] for r in json.loads((ROOT/'tmp/roa_full_training_schedule_20261106.json').read_text())['sessions']]
        cls.args=dict(root=ROOT,manifest_path=MANIFEST,manifest_sha256=sha256((ROOT/MANIFEST).read_bytes()).hexdigest(),calendar_sessions=cls.sessions,completed_through='2026-11-05')
        cls.artifact=generate_month_selection(**cls.args)

    def test_actual_month_reproduces_frozen_selection(self):
        old=json.loads((ROOT/'tmp/roa_november_signal_20261106.json').read_text())
        self.assertEqual(self.artifact['selection'],old['selection'])
        self.assertEqual(self.artifact['weights'],old['selected_weights'])

    def test_future_month_end_and_changed_manifest_reject(self):
        with self.assertRaisesRegex(ValueError,'WAIT_COMPLETED_MONTH_END'):
            generate_month_selection(**dict(self.args,completed_through='2026-10-29'))
        with self.assertRaisesRegex(ValueError,'MONTH_SOURCE_CHANGED'):
            generate_month_selection(**dict(self.args,manifest_sha256='0'*64))

    def test_incomplete_calendar_and_253_wrong_days_reject(self):
        with self.assertRaisesRegex(ValueError,'WAIT_FULL_TRAINING_CALENDAR'):
            generate_month_selection(**dict(self.args,calendar_sessions=[d for d in self.sessions if d>='2026-09-22']))
        with TemporaryDirectory(dir=ROOT/'tmp') as directory:
            manifest=json.loads((ROOT/MANIFEST).read_text())
            manifest['training_dates'][0]='2025-10-28'
            path=Path(directory)/'bad.json';path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'MONTH_TRAINING_CALENDAR_MISMATCH'):
                generate_month_selection(**dict(self.args,manifest_path=str(path.relative_to(ROOT)),manifest_sha256=sha256(path.read_bytes()).hexdigest()))

    def test_load_new_month_and_existing_holding_handoff(self):
        with TemporaryDirectory(dir=ROOT/'tmp') as directory:
            path=Path(directory)/'selection.json';path.write_text(json.dumps(self.artifact))
            loader=RoaMonthlySelectionLoader(root=ROOT,registry={'2026-11':dict(path=str(path.relative_to(ROOT)),sha256=sha256(path.read_bytes()).hexdigest())})
            month=loader('2026-11-02')
            with self.assertRaisesRegex(ValueError,'WAIT_NEW_MONTH_SIGNAL'):loader('2026-12-01')
            lifecycle=RoaExecutionLifecycle(path=Path(directory)/'state.json',account_id='test',strategy_epoch='test',contract_sha256='a'*64)
            account=dict(account_id='test',cash_confirmation_valid=True,shares={'OLD':14},total_uninvested_cash='1000',revision='r')
            before=deepcopy(account)
            def plan(day,decision,weights):
                return lifecycle.plan(signal=dict(signal_id=day,signal_date=decision,decision_date=decision,risk_on=True,weights=weights),session=day,
                    open_at=day+'T14:30:00Z',open_until=day+'T14:35:00Z',close_at=day+'T20:55:00Z',close_until=day+'T21:00:00Z')
            prior=plan('2026-10-01','2026-09-30',{'OLD':'1/10'})
            lifecycle.materialize_open(event_id=prior['events'][-1]['event_id'],account=account,opening_prices={'OLD':'10'},now='2026-10-01T14:31:00Z')
            state=plan('2026-11-02',month['decision_date'],month['weights'])
            event=state['events'][-1];self.assertEqual(event['reason'],'MONTHLY_TARGET')
            target=lifecycle.materialize_open(event_id=event['event_id'],account=account,opening_prices={s:'10' for s in {'OLD',*month['weights']}},now='2026-11-02T14:31:00Z')
            self.assertNotIn('OLD',target['targets'])
            self.assertEqual(len(target['targets']),10)
            self.assertEqual(account,before)
            self.assertEqual(lifecycle.materialize_open(event_id=event['event_id'],account=account,opening_prices={},now='2026-11-02T14:32:00Z'),target)


if __name__=='__main__':unittest.main()
