import json
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import subprocess
import sys
import re
from unittest.mock import patch

from data.current_quantity_v2_current_cash_plan import canonical
from scripts.publish_monthly_market_configuration import publish
from scripts.prepare_monthly_captured_training import build
from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration
from data.current_quantity_v2_monthly_training import build_monthly_training_package
from test_current_quantity_v2_paper_chain import ready
from test_prepare_monthly_captured_training import fixture


def inputs(folder):
    preparation = fixture(folder); root = Path(folder); pins = {}
    manifest, _, _ = build(**preparation)
    def put(path, value):
        raw = canonical(value); (root/path).write_bytes(raw); pins[path] = sha256(raw).hexdigest()
    # Deliberately tiny synthetic schedule: tests do not certify a real calendar.
    put('synthetic-evidence.json', {'synthetic': True})
    refs = ['synthetic-evidence.json']
    put('boundary.json', dict(decision_date='2026-11-02', target_month='2026-12',
        active_date='2026-12-01', decision_close_at='2026-11-02T16:00:00-05:00',
        active_open_at='2026-12-01T09:30:00-05:00', source_references=refs,
        training_dates=manifest['training_dates']))
    put('schedule.json', dict(schema='SCHEDULED_REGULAR_SESSIONS_V1',
        calendar=['2026-11-02','2026-12-01'], source_hashes={refs[0]:pins[refs[0]]},
        sessions=[dict(date=d, open_at=d+'T09:30:00-05:00', close_at=d+'T16:00:00-05:00')
                  for d in ['2026-11-02','2026-12-01']]))
    put('new-identities.json', json.loads((root/'identities.json').read_bytes()))
    held = json.loads((root/'A.held').read_bytes())
    held['chart']['result'][0]['timestamp'] = [int(datetime.fromisoformat('2026-11-02T21:00:00+00:00').timestamp())]
    put('new-held.json', held)
    put('review.json', dict(schema='MONTHLY_KNOWN_SOURCE_REVIEW_V1', decision_date='2026-11-02',
        reviewed_at='2026-11-03T10:30:00+00:00', source_references=refs,
        reviewed_members=['BBB','CCC'], unresolved=[]))
    return dict(preparation_arguments=preparation, supplemental_hashes=pins,
        calendar_path='boundary.json', schedule_path='schedule.json',
        identities_path='new-identities.json', held_bar_sources={'A':'new-held.json'}, review_path='review.json',
        output_directory='published')


class PublisherTests(unittest.TestCase):
    def test_cli_real_utc_past_capture_and_safe_failure(self):
        with TemporaryDirectory() as folder:
            request = inputs(folder); root = Path(folder)
            request['preparation_arguments'].pop('root'); request['preparation_arguments'].pop('clock')
            # Move this synthetic graph back exactly 52 weeks, including raw
            # timestamps and all referenced hashes. No product clock override.
            originals = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            objects = {}
            def shift(value, key=None):
                if isinstance(value, dict): return {k:shift(v,k) for k,v in value.items()}
                if isinstance(value, list): return [shift(v,key) for v in value]
                if isinstance(value, int) and (key == 'timestamp' or key == 'date'):
                    return value - 364*86400
                if isinstance(value, str):
                    return re.sub(r'\b202[0-9]-\d{2}-\d{2}',
                        lambda m:(datetime.fromisoformat(m[0])-timedelta(days=364)).date().isoformat(), value)
                return value
            for p,raw in originals.items():
                try: objects[p] = shift(json.loads(raw))
                except (ValueError, UnicodeDecodeError): pass
            # target_month is derived from active_date, not shifted as a date.
            objects[root/'boundary.json']['target_month'] = objects[root/'boundary.json']['active_date'][:7]
            bodies = {p:canonical(obj) for p,obj in objects.items()}
            def replace_hashes(value, mapping):
                if isinstance(value, dict): return {k:replace_hashes(v,mapping) for k,v in value.items()}
                if isinstance(value, list): return [replace_hashes(v,mapping) for v in value]
                return mapping.get(value,value) if isinstance(value,str) else value
            for _ in range(20):
                mapping = {sha256(originals[p]).hexdigest():sha256(raw).hexdigest() for p,raw in bodies.items()}
                updated = {p:canonical(replace_hashes(obj,mapping)) for p,obj in objects.items()}
                if updated == bodies: break
                bodies = updated
            else: self.fail('synthetic source graph did not converge')
            for p,raw in bodies.items(): p.write_bytes(raw)
            request = replace_hashes(request,mapping)
            raw = canonical(request); (root/'request.json').write_bytes(raw)
            command = [sys.executable,'-X','utf8','-E','-B','-m',
                'scripts.publish_monthly_market_configuration','--root',str(root),
                '--request','request.json','--request-sha256',sha256(raw).hexdigest()]
            result = subprocess.run(command,capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'],'PUBLISHED_CONDITIONAL_NOT_ACTIVATED')
            again = subprocess.run(command,capture_output=True,text=True,timeout=45)
            self.assertEqual(again.returncode,1)
            self.assertEqual(json.loads(again.stdout)['reason'],'CREATE_ONLY_OUTPUT_EXISTS')
            request['preparation_arguments']['clock'] = 'SECRET_CLOCK_OVERRIDE'
            raw = canonical(request); (root/'request.json').write_bytes(raw); command[-1] = sha256(raw).hexdigest()
            bad = subprocess.run(command,capture_output=True,text=True,timeout=45)
            self.assertEqual(bad.returncode,1)
            self.assertNotIn('SECRET',bad.stdout+bad.stderr); self.assertNotIn(str(root),bad.stdout+bad.stderr)
            command[-1] = '0'*64
            mismatch = subprocess.run(command,capture_output=True,text=True,timeout=45)
            self.assertEqual(mismatch.returncode,1)
            self.assertEqual(json.loads(mismatch.stdout)['status'],'BLOCKED')

    def test_actual_capture_compiler_and_reader_no_search_create_only(self):
        with TemporaryDirectory() as folder:
            args = inputs(folder)
            with patch('subprocess.run', side_effect=AssertionError('no search')):
                result = publish(**args)
            self.assertEqual(result['compiler_status'], 'READY_CONDITIONAL')
            self.assertFalse(result['service_activated'])
            self.assertEqual(result['search_calls'], 0)
            config = MonthlyFileConfiguration(root=folder, path=result['config_path'],
                sha256_value=result['config_sha256'], clock=lambda:datetime.fromisoformat('2026-12-01T15:00:00+00:00'))
            supplied = config.market_reader(None); package = supplied.pop('source_package')
            state = ready()[0]; before = deepcopy(state)
            review = dict(account_id=state['ledger']['account_id'],state_revision=state['ledger']['revision'],
                pending_rights=[],reviewed_at='2026-11-03T10:30:00+00:00',source_references=['synthetic-evidence.json'])
            raw = canonical(review); package['files']['test-account-review.json'] = raw
            package['source_hashes']['test-account-review.json'] = sha256(raw).hexdigest()
            with patch('subprocess.run', side_effect=AssertionError('no search')):
                wrapped = build_monthly_training_package(state, package, **supplied,
                    account_review_path='test-account-review.json', now='2026-12-01T15:00:00+00:00')
            self.assertIn('training', wrapped['documents']); self.assertEqual(state, before)
            with self.assertRaisesRegex(ValueError, 'CREATE_ONLY'): publish(**args)

    def test_future_raw_and_bad_boundary_reject_before_publish(self):
        for mode in ('future', 'boundary', 'missing_raw', 'review_missing_member', 'missing_training', 'drift_training', 'capture_schedule'):
            with self.subTest(mode=mode), TemporaryDirectory() as folder:
                args = inputs(folder); root = Path(folder)
                if mode == 'future':
                    args['preparation_arguments']['clock'] = lambda: datetime.fromisoformat('2026-11-02T12:00:00+00:00')
                elif mode == 'missing_raw': (root/'new/BBB.response.bin').unlink()
                else:
                    name = 'review.json' if mode == 'review_missing_member' else 'boundary.json'
                    value = json.loads((root/name).read_bytes())
                    if mode == 'boundary': value['decision_date'] = '2026-10-30'
                    elif mode == 'missing_training': value.pop('training_dates')
                    elif mode == 'drift_training': value['training_dates'][0] = '2020-01-01'
                    elif mode == 'capture_schedule':
                        value['decision_close_at'] = '2026-11-02T15:00:00-05:00'
                        schedule = json.loads((root/'schedule.json').read_bytes())
                        schedule['sessions'][0]['close_at'] = value['decision_close_at']
                        raw = canonical(schedule); (root/'schedule.json').write_bytes(raw)
                        args['supplemental_hashes']['schedule.json'] = sha256(raw).hexdigest()
                    else: value['reviewed_members'] = ['BBB']
                    raw = canonical(value); (root/name).write_bytes(raw)
                    args['supplemental_hashes'][name] = sha256(raw).hexdigest()
                with self.assertRaises((ValueError, FileNotFoundError)): publish(**args)
                self.assertFalse((root/'published').exists())

    def test_explicit_unresolved_issuer_blocks_even_different_ticker(self):
        with TemporaryDirectory() as folder:
            args = inputs(folder); root = Path(folder)
            value = json.loads((root/'review.json').read_bytes())
            value['unresolved'] = [dict(ticker='TRI', security_id='historical-other-id',
                issuer_id='IB', reason='UNRESOLVED_NOMINAL_COORDINATE',
                source_references=['synthetic-evidence.json'])]
            raw = canonical(value); (root/'review.json').write_bytes(raw)
            args['supplemental_hashes']['review.json'] = sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError, 'KNOWN_SOURCE_CONTRADICTION'): publish(**args)
            self.assertFalse((root/'published').exists())


if __name__ == '__main__': unittest.main()
