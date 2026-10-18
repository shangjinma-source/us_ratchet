"""Run the actual table renderer offline; no browser, API or live state writes."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node required for actual JS renderer')
class PlannerExclusionRuntimeTests(unittest.TestCase):
    def render(self, *, budget=118, gap=1000, cash=1000):
        source = (Path(__file__).resolve().parents[1] / 'web/index.html').read_text(encoding='utf-8')
        def function_span(start, following):
            self.assertEqual(source.count(start), 1)
            self.assertEqual(source.count(following), 1)
            return start + source.split(start, 1)[1].split(following, 1)[0]
        renderer = function_span('function renderPlannerTable(', 'function allocatePlannerRows(')
        price_fee = function_span('function plannerItemPrice(', 'function plannerAffordableNotional(')
        javascript = '\n'.join([
            'const PLANNER_LOT_SIZE=1, PLANNER_COMPACT_TARGET=4, PLANNER_EXECUTION_VENUE="saved";',
            'const fmt0=x=>String(x), fmt=x=>String(x), esc=x=>String(x);',
            price_fee, renderer,
            'const html=[];',
            'const policy={allow_fractional:false,lot_size:1,fee_bps:0,min_fee:0,max_names:1,compact_target:4};',
            'const item=' + json.dumps(dict(ticker='MSFT', limit=498.43, amount=budget, _gap=gap)) + ';',
            f'renderPlannerTable(html, [], {cash}, {cash}, {{policy, candidates:[item]}});',
            'process.stdout.write(html.join(""));',
        ])
        result = subprocess.run(['node'], input=javascript, encoding='utf-8', capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_sub_lot_budget_not_mislabelled_as_candidate_cap(self):
        for cash in (1000, 10000):
            rendered = self.render(cash=cash)
            self.assertIn('MSFT：原策略预算 $118，不足 1 个交易单位约 $498.43', rendered)
            self.assertNotIn('MSFT：超过本次最多', rendered)

    def test_gap_cash_and_cap_remain_distinct(self):
        self.assertIn('超过真实缺口 $50', self.render(budget=1000, gap=50))
        self.assertIn('本次现金不足以成交', self.render(budget=1000, cash=100))
        self.assertIn('超过本次最多 4 个候选', self.render(budget=1000))


if __name__ == '__main__':
    unittest.main()
