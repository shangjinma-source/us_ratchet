"""Transport/source integration; policy validation is isolated at its tested seam."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from core.strategy_account_ledger import canonical, replay
from data.saved_frontier_first_window_v1 import SOURCES
from data.saved_frontier_supplement_request_v1 import prepare_frontier_supplement_request
from data.saved_frontier_source_reader_v1 import read_and_apply_frontier_capture
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_monthly_supplement_capture import capture_supplement
from data.saved_frontier_live_reader_v1 import SavedFrontierLiveReader
from test_strategy_daily_first_window_v3 import FirstWindowTests, ROOT


class FrontierReaderTests(unittest.TestCase):
    def test_real_capture_baseline_closure_reader_and_risk_store(self):
        with TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            case, config, captured = FirstWindowTests().case(folder)
            captured['official.response.bin'] = captured['official.response.bin'].replace(
                b'<channel>', b'<channel><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate>')
            daily = json.loads(captured['daily.response.bin'])
            series = daily['chart']['result'][0]
            series['indicators']['quote'][0]['close'][-1] = 80
            series['indicators']['adjclose'][0]['adjclose'][-1] = 80
            captured['daily.response.bin'] = canonical(daily)
            state = replay(case.state['account_id'], [row['payload'] for row in case.state['events']
                if row['payload'].get('order_id') != 'a-pending'])
            target = deepcopy(case.target)
            target['payload']['target_quantities'] = {'B': 0}
            selected = target['payload']['decision']['payload']
            selected['target_quantities'] = {'B': 0}
            target['payload']['decision']['decision_id'] = sha256(canonical(selected)).hexdigest()
            target['target_id'] = sha256(canonical(target['payload'])).hexdigest()
            proposal = dict(proposal_id='validated-policy-seam', payload=dict(proposed_target_quantities={'B': 7}))
            for module in ('saved_frontier_supplement_request_v1', 'saved_frontier_first_window_v1', 'saved_frontier_exit_packet_v1'):
                stack.enter_context(patch('data.'+module+'.build_frontier_proposal', return_value=proposal))
            pins = []
            for name in SOURCES:
                raw = (ROOT/name).read_bytes()
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                pins.append(dict(path=name, sha256=sha256(raw).hexdigest()))
            now = case.clock[0]
            prepared = prepare_frontier_supplement_request(root=root, state=state, target=target,
                proposal=proposal, risk_state=None, identity_reference=config['identity'],
                calendar_reference=config['calendar'], unit_source_paths=config['unit_source_paths'],
                source_pins=pins, decision_date='2026-10-30', now=now)
            self.assertEqual(prepared['status'], 'SUPPLEMENT_REQUEST_PREPARED')
            binding = prepared['binding']
            capture = capture_supplement(directory=root/'capture-new', request=prepared['request'],
                binding=binding, read_binding=lambda: binding, execute=True,
                clock=lambda: now-timedelta(seconds=10),
                fetch_daily=lambda *args: dict(status=200, body=captured['daily.response.bin']),
                fetch_official=lambda: dict(status=200, body=captured['official.response.bin']))
            store = MonthlyPeakExitStore(root/'frontier-risk.sqlite')
            args = dict(root=root, prepared=prepared, capture=capture, state=state,
                target=target, proposal=proposal, risk_store=store, now=now)
            result = read_and_apply_frontier_capture(**args)
            self.assertEqual(result['risk_result']['effective_target_quantities'], {'B': 0})
            self.assertEqual(result['risk_result']['monthly_cap_view']['target_quantities'], {'B': 7})
            repeated = read_and_apply_frontier_capture(**args)
            self.assertIn('B', repeated['risk_result']['state']['exited'])
            self.assertFalse(result['review']['coverage_complete'])
            self.assertEqual(target['payload']['target_quantities'], {'B': 0})
            with self.assertRaises(ValueError):
                read_and_apply_frontier_capture(**dict(args, now=now+timedelta(days=1)))
            missing = deepcopy(capture)
            missing['files'].pop(next(iter(missing['files'])))
            with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_SOURCE_BUDGET'):
                read_and_apply_frontier_capture(**dict(args, capture=missing))
            live_state = deepcopy(state)
            view = SimpleNamespace(monthly=SimpleNamespace(
                accounts=SimpleNamespace(read=lambda: live_state), current=lambda: target),
                require_proposal=lambda **kwargs: proposal)
            release = canonical(dict(authorized=True, authorized_at=now.isoformat(), policy_id='SAVED_FRONTIER_CAP50_EXIT20_V1',
                monthly_cap='1/2', exit_ratio='4/5', sma20_overlay=False))
            live = SavedFrontierLiveReader(root=root, monthly_view=view, risk_store=store,
                source_configuration=dict(identity=config['identity'], calendar=config['calendar'],
                    target_evidence_root='capture'), source_pins=pins,
                capture_root=root/'live-capture', archive_root=root/'live-archive',
                release_bytes=release, clock=lambda: now, validate_sources=lambda: None,
                fetch_daily=lambda *args: dict(status=200, body=captured['daily.response.bin']),
                fetch_official=lambda: dict(status=200, body=captured['official.response.bin']))
            emitted = live(state, target, now, proposal=proposal)
            self.assertEqual(emitted['status'], 'DAILY_SIGNAL_READY')
            self.assertEqual(emitted['risk_projection']['state'], store.read(state['account_id']))
            repeat = live(state, target, now, proposal=proposal)
            self.assertEqual(repeat['signal']['effective_target_quantities'], {'B': 0})
            live_state['revision'] = 'concurrently-changed'
            with self.assertRaisesRegex(ValueError, 'FRONTIER_CAPTURE_SNAPSHOT_CHANGED'):
                live(state, target, now, proposal=proposal)
            live_state['revision'] = state['revision']
            live.capture_root = root/'concurrent-capture'
            before_risk = store.read(state['account_id'])
            def changed_during_fetch(*args):
                live_state['revision'] = 'changed-during-network'
                return dict(status=200, body=captured['daily.response.bin'])
            live.fetch_daily = changed_during_fetch
            with self.assertRaisesRegex(ValueError, 'FRONTIER_CAPTURE_SNAPSHOT_CHANGED'):
                live(state, target, now, proposal=proposal)
            self.assertEqual(store.read(state['account_id']), before_risk)
