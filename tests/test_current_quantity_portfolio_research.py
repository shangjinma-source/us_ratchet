import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from data import current_quantity_portfolio_research as module


def witness(cash):
    q = int(float(cash) // 10)
    return dict(status='BUDGET_STOPPED', entered_cash=str(cash), decision_date='2026-10-12', selected=dict(quantities={'s': q} if q else {}, fees='0',
                residual_cash=str(float(cash) - 10*q), notional=str(10*q), actual_k=int(q > 0),
                actual_weights={'s': str(10*q/float(cash))} if q else {}))


class QuantityServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pins = {}
        args = dict(prices={'s': '10'}, metadata={'s': dict(ticker='X', issuer_id='i')}, entered_cash='20000',
                    fee_bps='0', minimum_cash_buffer='0', max_objective_evaluations=8192,
                    training_scenarios=[{'s': '1'}]*12, scenario_dates=[f'2026-01-{day:02d}' for day in range(1,13)], decision_date='2026-10-12', fixed_seed='fixture')
        self.put(module.CORE, b'fixture core')
        self.put(module.INPUT, args)
        self.put(module.RESULT, witness('20000'))
        self.put(module.START, dict(core_sha256=self.pins[module.CORE], inputs_sha256=self.pins[module.INPUT]))
        self.put(module.RECEIPT, dict(result_sha256=self.pins[module.RESULT], source_registration={'source_pins': {}}))
        self.put(module.READBACK, dict(status='PASS_ALL_SAVED_BEST_WITNESSES_AND_SOURCE_ACCOUNTING', selected_ticker_quantities={'X': 2000}))
        self.put(module.PANEL, dict(calendar=['2026-10-12'], stocks=[dict(ticker='X', values=[[10,11,9,10,100]])]))
        self.calls = []
        def stub(**kwargs):
            self.calls.append(kwargs)
            return witness(kwargs['entered_cash'])
        self.service = module.CurrentQuantityPortfolioResearch(self.root, self.pins, stub)

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = data if isinstance(data, bytes) else json.dumps(data).encode()
        path.write_bytes(raw)
        self.pins[name] = hashlib.sha256(raw).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def test_seed_and_amount_enters_core_cache_copy(self):
        seed = self.service.calculate(20000)
        self.assertEqual(seed['origin'], 'SEALED_SEED')
        self.assertEqual(self.calls, [])
        value = self.service.calculate(500)
        self.assertEqual(self.calls[0]['entered_cash'], '500.00')
        self.assertEqual(self.calls[0]['max_objective_evaluations'], 8192)
        self.assertEqual(value['invested'] + value['cash'] + value['fees'], 500)
        value['stocks'].clear()
        cached = self.service.calculate('500.00')
        self.assertEqual(cached['origin'], 'MEMORY_CACHE')
        self.assertEqual(len(cached['stocks']), 1)
        self.assertEqual(len(self.calls), 1)

    def test_changed_source_fail_closed_and_missing_init(self):
        self.service.calculate(20000)
        (self.root / module.INPUT).write_text('{}')
        with self.assertRaises(module.PreviewSourceError):
            self.service.calculate(20000)
        self.assertEqual(len(self.service.results), 0)
        with self.assertRaises(module.PreviewSourceError):
            module.CurrentQuantityPortfolioResearch(self.root / 'missing', self.pins).calculate(20000)

    def test_chart_membership_and_all_cash(self):
        seed = self.service.calculate(20000)
        self.assertEqual(len(self.service.bars(seed['research_id'], 'X')['bars']), 1)
        with self.assertRaises(module.PreviewSourceError):
            self.service.bars(seed['research_id'], 'Y')
        cash = self.service.calculate(5)
        self.assertEqual(cash['status'], 'ALL_CASH')
        self.assertEqual(cash['cash'], 5)
        self.service.search = lambda **kwargs: dict(status='INCOMPLETE', selected=None, entered_cash=kwargs['entered_cash'], decision_date=kwargs['decision_date'])
        incomplete = self.service.calculate(7)
        self.assertEqual(incomplete['status'], 'INCOMPLETE')
        self.assertNotIn(incomplete['research_id'], self.service.results)


if __name__ == '__main__':
    unittest.main()
