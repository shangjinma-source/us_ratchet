import json
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from test_coordinate_monthly_simulation import setup
from scripts.coordinate_monthly_simulation import run
from scripts.prepare_monthly_captured_training import build
from scripts.build_monthly_successor_plan import build_next_plan, prepare
from data.current_quantity_v2_current_cash_plan import canonical


def fixture(directory):
    root, settings, _, args, calls, _ = setup(directory)
    assert run(**args, execute=True)['status'] == 'WAITING_REVIEW'
    def save(path, value):
        raw = canonical(value); (root/path).write_bytes(raw); return sha256(raw).hexdigest()
    # Entirely synthetic calendar; production builder must never invent these dates.
    days = []
    day = datetime(2026, 11, 2)
    while day <= datetime(2027, 1, 1):
        if day.weekday() < 5: days.append(day.date().isoformat())
        day += timedelta(days=1)
    proof = save('synthetic-calendar-proof.json', {'synthetic': True})
    schedule = dict(schema='SCHEDULED_REGULAR_SESSIONS_V1', calendar=days,
        sessions=[dict(date=d, timezone='America/New_York', open_at=d+'T09:30:00-05:00',
                       close_at=d+'T16:00:00-05:00') for d in days],
        source_hashes={'synthetic-calendar-proof.json': proof})
    calendar_hash = save('successor-calendar.json', schedule)
    arguments = dict(root=root, previous_manifest_path='prepared/manifest.json',
        previous_manifest_sha256=sha256((root/'prepared/manifest.json').read_bytes()).hexdigest(),
        previous_completion_path='stages/prepare.complete.json',
        previous_completion_sha256=sha256((root/'stages/prepare.complete.json').read_bytes()).hexdigest(),
        calendar_path='successor-calendar.json', calendar_source_hashes={
            'successor-calendar.json': calendar_hash, 'synthetic-calendar-proof.json': proof},
        output_directory='next-month', clock=args['clock'])
    return root, arguments, schedule, calls, save


class SuccessorPlanTests(unittest.TestCase):
    def test_completed_predecessor_to_real_validator_and_training_build(self):
        with TemporaryDirectory() as directory:
            root, args, schedule, calls, save = fixture(directory)
            result = build_next_plan(**args)
            self.assertEqual(result['target_month'], '2026-12')
            self.assertEqual(len(calls), 1)
            for path, raw in result['artifacts'].items():
                (root/path).parent.mkdir(parents=True, exist_ok=True); (root/path).write_bytes(raw)
            plan_path = 'next-month/capture_plan.json'; plan_hash = sha256((root/plan_path).read_bytes()).hexdigest()
            plan, checked = prepare(plan_path, plan_hash, root=root, clock=args['clock'])
            self.assertFalse(checked['ready_after_close'])
            self.assertEqual(plan['session'], '2026-11-30')
            old = json.loads((root/'prepared/manifest.json').read_bytes())
            body = json.loads((root/old['candidates'][0]['training_source']).read_bytes())
            chart = body['chart']['result'][0]
            for day in schedule['calendar']:
                if '2026-11-02' < day <= '2026-11-30':
                    chart['timestamp'].append(int(datetime.fromisoformat(day+'T21:00:00+00:00').timestamp()))
                    for values in chart['indicators']['quote'][0].values(): values.append(values[-1]+1)
            clock = lambda: datetime.fromisoformat('2026-12-01T12:00:00+00:00')
            fetch = lambda url, **kw: dict(raw=canonical(body), http_status=200, final_url=url, response_headers={})
            # Exercise real coordinator -> capture -> prepare dispatcher, no patched validators.
            config = json.loads((root/'coordinator.json').read_bytes())
            config.update(settings_path='next-month/settings.json',
                settings_sha256=sha256((root/'next-month/settings.json').read_bytes()).hexdigest(),
                session='2026-12-01', daily_output='next-month/daily.json', stage_directory='next-month/stages')
            config_hash = save('next-coordinator.json', config)
            coordinated = run(config_path=root/'next-coordinator.json', config_sha256=config_hash,
                              clock=clock, fetch=fetch, execute=True)
            self.assertEqual(coordinated['status'], 'WAITING_REVIEW')
            index = 'next-month/capture/completion_index.json'
            manifest, compiled, _ = build(root=root, previous_manifest_path=args['previous_manifest_path'],
                previous_manifest_sha256=args['previous_manifest_sha256'], capture_index_path=index,
                capture_index_sha256=sha256((root/index).read_bytes()).hexdigest(),
                plan_path=plan_path, plan_sha256=plan_hash, clock=clock, plan_validator=prepare)
            self.assertEqual(compiled['status'], 'READY_CONDITIONAL')
            self.assertEqual(manifest['decision_date'], '2026-11-30')
            self.assertEqual(manifest['membership_observation_asof'], '2026-10-30')
            self.assertFalse(manifest['full_pit_verified'])
            self.assertEqual(len(manifest['training_dates']), 253)
            # A second successor must replay the full completed chain, not merely
            # accept a later decision_date in a hand-written manifest.
            next_manifest = 'next-month/prepared/manifest.json'
            self.assertEqual(json.loads((root/next_manifest).read_bytes()), manifest)
            next_hash = sha256((root/next_manifest).read_bytes()).hexdigest()
            receipt_path = 'next-month/stages/prepare.complete.json'
            receipt_hash = sha256((root/receipt_path).read_bytes()).hexdigest()
            second = build_next_plan(**{**args, 'previous_manifest_path':next_manifest,
                'previous_manifest_sha256':next_hash, 'previous_completion_path':receipt_path,
                'previous_completion_sha256':receipt_hash, 'output_directory':'third-month', 'clock':clock})
            self.assertEqual(second['target_month'], '2027-01')
            for path, raw in second['artifacts'].items():
                (root/path).parent.mkdir(parents=True, exist_ok=True); (root/path).write_bytes(raw)
            second_path = 'third-month/capture_plan.json'
            _, checked = prepare(second_path, sha256((root/second_path).read_bytes()).hexdigest(), root=root, clock=clock)
            self.assertFalse(checked['ready_after_close'])

    def test_missing_calendar_boundary_and_tampered_completed_manifest_rejected(self):
        with TemporaryDirectory() as directory:
            root, args, schedule, calls, save = fixture(directory)
            truncated = dict(schedule, calendar=schedule['calendar'][:1], sessions=schedule['sessions'][:1])
            args['calendar_source_hashes']['successor-calendar.json'] = save('successor-calendar.json', truncated)
            with self.assertRaisesRegex(ValueError, 'NEXT_MONTH_BOUNDARY_UNAVAILABLE'):
                build_next_plan(**args)
            args['calendar_source_hashes']['successor-calendar.json'] = save('successor-calendar.json', schedule)
            manifest = json.loads((root/args['previous_manifest_path']).read_bytes())
            manifest['decision_date'] = '2026-11-03'
            args['previous_manifest_sha256'] = save(args['previous_manifest_path'], manifest)
            with self.assertRaisesRegex(ValueError, 'NOT_COMPLETED_OUTPUT'):
                build_next_plan(**args)
            self.assertEqual(len(calls), 1)

    def test_missing_original_source_blocks_successor_lineage(self):
        with TemporaryDirectory() as directory:
            root, args, _, calls, _ = fixture(directory)
            build_next_plan(**args)
            # A completed manifest and its receipt alone cannot replace original raw evidence.
            prior = json.loads((root/'previous.json').read_bytes())
            (root/prior['candidates'][0]['training_source']).unlink()
            with self.assertRaises((ValueError, FileNotFoundError)):
                build_next_plan(**args)
            self.assertEqual(len(calls), 1)

    def test_calendar_missing_next_month_must_not_skip_forward(self):
        with TemporaryDirectory() as directory:
            root, args, schedule, _, save = fixture(directory)
            days = ['2026-11-02', '2026-12-01', '2027-02-01']
            schedule.update(calendar=days, sessions=[dict(date=d,timezone='America/New_York',
                open_at=d+'T09:30:00-05:00',close_at=d+'T16:00:00-05:00') for d in days])
            args['calendar_source_hashes']['successor-calendar.json'] = save('successor-calendar.json', schedule)
            with self.assertRaisesRegex(ValueError, 'MISSING_NEXT_MONTH_CALENDAR'):
                build_next_plan(**args, completed_target_month='2026-12')


if __name__ == '__main__':
    unittest.main()
