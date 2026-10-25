from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.preflight_quantity_v2_forward_registration import preflight, dependency_closure, merge_pins, ENTRYPOINTS


class ForwardPreflightTests(unittest.TestCase):
    def fixture(self, root):
        def write(name, value):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(value).encode()
            path.write_bytes(raw)
            return dict(path=name, sha256=sha256(raw).hexdigest())
        pins = {}
        for name in ENTRYPOINTS:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('import datetime\n')
            pins[name] = sha256(path.read_bytes()).hexdigest()
        fees = write('fees.json', {'fixed_per_order': '0', 'notional_rate': '0'})
        provenance = write('calendar-source.json', {'source': 'synthetic'})
        calendar = write('calendar.json', dict(source_hashes={provenance['path']:provenance['sha256']}, sessions=[dict(date='2099-01-05',
            open_at='2099-01-05T09:30:00-05:00', close_at='2099-01-05T16:00:00-05:00')]))
        identity = write('identity.json', {'identity': 'synthetic'})
        descriptor = write('descriptor.json', dict(source_hashes={**pins, identity['path']:identity['sha256']}))
        initial = write('initial.json', dict(source_hashes={}))
        policy = dict(rebound_fraction='1/2', minimum_discount='1/200', maximum_age_seconds=120)
        bootstrap = dict(root=str(root), database_path=str(root/'absent.sqlite3'), simulation_id='trial',
                         pullback=dict(policy=policy), fees=fees, schedule=calendar, descriptor=descriptor,
                         initial_month=initial, identity_manifest_path=identity['path'],
                         initial_cash='20000', model='STRICT_CROSS_FULL_FILL_AT_LIMIT', scope='CONDITIONAL')
        daily = dict(root=str(root), database_path=bootstrap['database_path'], simulation_id='trial',
                     pullback=bootstrap['pullback'], fees_path=fees['path'], fees_sha256=fees['sha256'],
                     schedule_path=calendar['path'], schedule_sha256=calendar['sha256'], monthly=None)
        return dict(schema='QUANTITY_V2_FORWARD_PREFLIGHT_REQUEST_V1',
            protocol=write('protocol.json', dict(status='NOT_ACTIVATED', frozen=False,
                activation=dict(registered_at=None), execution=policy)),
            bootstrap=write('bootstrap.json', bootstrap), daily=write('daily.json', daily),
            dependencies=write('deps.json', dict(source_hashes=pins)), proposed_start_session='2099-01-05')

    def test_readonly_future_draft_not_ready_and_no_account_created(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); request = self.fixture(root)
            before = {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result = preflight(root=root, request=request)
            self.assertEqual(result['status'], 'NOT_READY')
            self.assertTrue(result['proposed_start_eligible'])
            self.assertFalse(result['registered'])
            self.assertFalse(result['account_writes'])
            self.assertEqual(before, {p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_past_start_rejected_without_clock_injection(self):
        with TemporaryDirectory() as folder:
            request = self.fixture(Path(folder)); request['proposed_start_session'] = '2020-01-01'
            result = preflight(root=folder, request=request)
            self.assertFalse(result['proposed_start_eligible'])

    def test_input_tamper_blocks(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); request = self.fixture(root)
            (root/'daily.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'INPUT_CHANGED'):
                preflight(root=root, request=request)

    def test_runtime_reference_tamper_blocks(self):
        for name, error in [('initial.json','INPUT_CHANGED'),
                            ('identity.json','DESCRIPTOR_SOURCE_CHANGED'),
                            ('calendar-source.json','CALENDAR_SOURCE_CHANGED')]:
            with self.subTest(name=name), TemporaryDirectory() as folder:
                root = Path(folder); request = self.fixture(root)
                (root/name).write_text('{}')
                with self.assertRaisesRegex(ValueError, error):
                    preflight(root=root, request=request)

    def test_transitive_unlisted_dependency_not_certified(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); (root/'entry.py').write_text('import dependency\n')
            (root/'dependency.py').write_text('import hidden\n')
            (root/'hidden.py').write_text('VALUE = 1\n')
            pins = {p.name:sha256(p.read_bytes()).hexdigest() for p in (root/'entry.py',root/'dependency.py')}
            result = dependency_closure(root, ['entry.py'], pins)
            self.assertIn('hidden.py', result['source_hashes'])
            self.assertFalse(result['complete'])
            self.assertTrue(any(x['path']=='hidden.py' for x in result['issues']))

    def test_package_relative_and_dynamic_imports(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); (root/'pkg').mkdir()
            (root/'entry.py').write_text('from pkg import module\n')
            (root/'pkg/__init__.py').write_text('')
            (root/'pkg/module.py').write_text('from . import child\n__import__("hidden")\n')
            (root/'pkg/child.py').write_text('import third_party_unknown\n')
            pins = {p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.py')}
            result = dependency_closure(root, ['entry.py'], pins)
            self.assertEqual(set(result['source_hashes']), set(pins))
            self.assertFalse(result['complete'])
            self.assertEqual({x['code'] for x in result['issues']}, {'DYNAMIC_CODE_REQUIRES_REVIEW','EXTERNAL_OR_UNRESOLVED_IMPORT'})

    def test_conflicting_initial_pin_maps_and_final_merge_rejected(self):
        with self.assertRaisesRegex(ValueError, 'REFERENCE_PIN_CONFLICT'):
            merge_pins({'source': 'a'*64}, {}, {'source': 'b'*64})
        with TemporaryDirectory() as folder:
            root = Path(folder); request = self.fixture(root)
            initial = dict(original_source_hashes={'fees.json':'a'*64},
                source_hashes={'fees.json':sha256((root/'fees.json').read_bytes()).hexdigest()})
            (root/'initial.json').write_text(json.dumps(initial))
            bootstrap = json.loads((root/'bootstrap.json').read_bytes())
            bootstrap['initial_month']['sha256'] = sha256((root/'initial.json').read_bytes()).hexdigest()
            (root/'bootstrap.json').write_text(json.dumps(bootstrap))
            request['bootstrap']['sha256'] = sha256((root/'bootstrap.json').read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, 'REFERENCE_PIN_CONFLICT'):
                preflight(root=root, request=request)

    def test_cross_date_calendar_cannot_qualify_future_start(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); request = self.fixture(root)
            calendar = json.loads((root/'calendar.json').read_bytes())
            calendar['sessions'][0].update(open_at='2099-01-04T09:30:00-05:00',
                                           close_at='2099-01-06T16:00:00-05:00')
            (root/'calendar.json').write_text(json.dumps(calendar))
            digest = sha256((root/'calendar.json').read_bytes()).hexdigest()
            for name in ('bootstrap', 'daily'):
                value = json.loads((root/(name+'.json')).read_bytes())
                if name == 'bootstrap': value['schedule']['sha256'] = digest
                else: value['schedule_sha256'] = digest
                (root/(name+'.json')).write_text(json.dumps(value))
                request[name]['sha256'] = sha256((root/(name+'.json')).read_bytes()).hexdigest()
            self.assertFalse(preflight(root=root, request=request)['proposed_start_eligible'])

    def test_stdlib_shadow_parent_is_traversed(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); (root/'json').mkdir()
            (root/'entry.py').write_text('import json.decoder\n')
            (root/'json/__init__.py').write_text('import hidden\n')
            (root/'hidden.py').write_text('VALUE=1\n')
            result = dependency_closure(root, ['entry.py'], {})
            self.assertIn('json/__init__.py', result['source_hashes'])
            self.assertIn('hidden.py', result['source_hashes'])
            self.assertTrue(any(x['code']=='UNRESOLVED_LOCAL_IMPORT' for x in result['issues']))

    def test_namespace_child_is_not_external(self):
        with TemporaryDirectory() as folder:
            root = Path(folder); (root/'pkg').mkdir()
            (root/'entry.py').write_text('from pkg import child\n')
            (root/'pkg/child.py').write_text('VALUE=1\n')
            pins={p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.py')}
            result = dependency_closure(root, ['entry.py'], pins)
            self.assertEqual(result['issues'], [])
            self.assertEqual(set(result['source_hashes']), set(pins))


if __name__ == '__main__':
    unittest.main()
