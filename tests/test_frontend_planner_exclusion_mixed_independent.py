"""Offline actual allocator plus actual renderer, with mixed planned/excluded rows."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node required')
class MixedPlannerTests(unittest.TestCase):
    def test_real_mixed_allocation_keeps_each_exclusion_reason(self):
        source = (Path(__file__).resolve().parents[1] / 'web/index.html').read_text(encoding='utf8')
        def span(start, end):
            self.assertEqual(source.count(start), 1)
            self.assertEqual(source.count(end), 1)
            return start + source.split(start, 1)[1].split(end, 1)[0]
        functions = [span('function plannerRowNote(', 'function currentMarketDate('),
                     span('function plannerPriorityValue(', 'function plannerAutoPolicy('),
                     span('function renderPlannerTable(', 'function renderGapQueue(')]
        items = [dict(ticker='BOUGHT', limit=100, amount=200, _gap=1000),
                 dict(ticker='BUDGET', limit=498.43, amount=118, _gap=1000),
                 dict(ticker='GAP', limit=200, amount=1000, _gap=50),
                 dict(ticker='CASH', limit=2000, amount=3000, _gap=3000),
                 dict(ticker='CAP', limit=200, amount=1000, _gap=1000)]
        javascript = '\n'.join([
            'const PLANNER_LOT_SIZE=1,PLANNER_COMPACT_TARGET=4,PLANNER_EXECUTION_VENUE="offline";',
            'const fmt0=x=>String(x),fmt=x=>String(x),esc=x=>String(x);', *functions,
            'const items=' + json.dumps(items) + ';',
            'const policy={allow_fractional:false,lot_size:1,fee_bps:0,min_fee:0,max_names:1,compact_target:1,max_single_amount:1000};',
            'const before=JSON.stringify(items);',
            'const result=allocatePlannerRows(items,1000,policy);const html=[];',
            'renderPlannerTable(html,result.planned,1000,result.remaining,{policy,candidates:items});',
            'process.stdout.write(JSON.stringify({html:html.join(""),result,unchanged:before===JSON.stringify(items)}));',
        ])
        run = subprocess.run(['node'], input=javascript, text=True, encoding='utf8', capture_output=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        value = json.loads(run.stdout)
        self.assertTrue(value['unchanged'])
        self.assertEqual(len(value['result']['planned']), 1)
        self.assertEqual(value['result']['planned'][0]['item']['ticker'], 'BOUGHT')
        self.assertEqual(value['result']['planned'][0]['shares'], 2)
        self.assertEqual(value['result']['remaining'], 800)
        html = value['html']
        self.assertIn('<strong>BOUGHT</strong>', html)
        self.assertNotIn('BOUGHT：', html)
        self.assertIn('BUDGET：原策略预算 $118，不足 1 个交易单位约 $498.43', html)
        self.assertNotIn('BUDGET：超过本次最多', html)
        self.assertIn('GAP：1 个交易单位约 $200，超过真实缺口 $50', html)
        self.assertIn('CASH：本次现金不足以成交 1 个交易单位', html)
        self.assertIn('CAP：超过本次最多 1 个候选的精简上限', html)


if __name__ == '__main__': unittest.main()
