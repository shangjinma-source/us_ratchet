from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_daily_security_domain_v1 import plan_security_domain
from data.strategy_paper_first_window_core_v2 import SOURCES, review_source_window
import test_strategy_daily_first_window_v3 as fixture


class PaperSourceWindowTests(unittest.TestCase):
    def case(self, folder):
        account, config, captured = fixture.FirstWindowTests().case(folder)
        root = Path(folder)
        pins = []
        for name in SOURCES:
            raw = (fixture.ROOT/name).read_bytes()
            path = root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            pins.append(dict(path=name, sha256=sha256(raw).hexdigest()))
        domain = plan_security_domain(root=root, state=account.state, target=account.target,
            identity_reference=config['identity'], source_paths=config['unit_source_paths'])
        entry = domain['securities']['B']
        baseline = entry['unit_baseline']
        names = set(baseline['source_hashes']) | {baseline['review_reference']['path']}
        files = {name: (root/config['unit_source_paths'][name]).read_bytes() for name in names}
        config.update(schema='PAPER_FIRST_DAILY_WINDOW_V2', source_pins=pins,
                      monthly_decision_date='2026-11-02')
        window = json.loads((root/'calendar.json').read_bytes())['sessions'][-21:-1]
        receipt = json.loads(captured['daily.receipt.json'])
        receipt['requested_from'] = (datetime.fromisoformat(window[0]['open'])-timedelta(days=1)).isoformat()
        captured['daily.receipt.json'] = canonical(receipt)
        raw = canonical(config)
        return account, dict(root=root, configuration_bytes=raw, configuration_sha256=sha256(raw).hexdigest(),
            capture_files=captured, account_id='independent-paper', account_revision='paper-revision',
            target_id='paper-target', target_month='2026-11', target_quantities={'B': 5},
            entry=entry, baseline_files=files, clock=lambda: account.clock[0], began=account.clock[0])

    def test_actual_source_rules_with_account_independent_context(self):
        with TemporaryDirectory() as folder:
            account, args = self.case(folder)
            before = account.store.path.read_bytes()
            result = review_source_window(**args)
            self.assertEqual(result['receipt']['account_id'], 'independent-paper')
            self.assertEqual(result['receipt']['target_id'], 'paper-target')
            self.assertIsNone(result['receipt']['release_sha256'])
            inputs = json.loads(result['files'][result['receipt']['normalized_inputs_path']])
            self.assertEqual(inputs['base_target']['quantities'], {'B': 5})
            self.assertEqual(len(inputs['histories']['B']['closes']), 20)
            self.assertEqual(account.store.path.read_bytes(), before)

    def test_changed_baseline_and_nonoverlapping_prices_rejected(self):
        with TemporaryDirectory() as folder:
            _, args = self.case(folder)
            bad = deepcopy(args)
            name = next(iter(bad['baseline_files']))
            bad['baseline_files'][name] += b' '
            with self.assertRaisesRegex(ValueError, 'FIRST_BASELINE_HASH'):
                review_source_window(**bad)
            bad = deepcopy(args)
            raw = json.loads(bad['capture_files']['daily.response.bin'])
            series = raw['chart']['result'][0]
            series['indicators']['quote'][0]['close'] = [101]*20
            series['indicators']['adjclose'][0]['adjclose'] = [101]*20
            body = canonical(raw)
            bad['capture_files']['daily.response.bin'] = body
            receipt = json.loads(bad['capture_files']['daily.receipt.json'])
            receipt.update(raw_sha256=sha256(body).hexdigest(), stored_bytes=len(body))
            bad['capture_files']['daily.receipt.json'] = canonical(receipt)
            with self.assertRaisesRegex(ValueError, 'WAIT_PRICE_CONTINUITY_REVIEW'):
                review_source_window(**bad)


if __name__ == '__main__':
    unittest.main()
