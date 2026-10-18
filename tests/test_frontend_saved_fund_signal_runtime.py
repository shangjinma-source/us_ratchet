"""Rehydrate one saved journal row into planner inputs; not a live UI test."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node required')
class SavedFundPlannerRuntimeTests(unittest.TestCase):
    def test_saved_sub_lot_signals_render_reason_for_both_cash_scenarios(self):
        snapshot_path = ROOT / 'data/cache/research/offline_saved_fund_signal_diagnostic_20260923_v1/snapshot.json'
        if not snapshot_path.exists():
            self.skipTest('Local research snapshot not distributed with repository')
        raw = snapshot_path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'c5b3da4db4a83c84200bdc085343e96e285533b861b1d3b1dd6cca83b564424e')
        snapshot = json.loads(raw)
        data = dict(execution=snapshot['execution'], execution_constraints=snapshot['execution_constraints'],
            account_readiness=dict(position_gaps=snapshot['account']['position_gaps']))
        source = (ROOT / 'web/index.html').read_text(encoding='utf-8')
        def span(start, end):
            self.assertEqual(source.count(start), 1)
            self.assertEqual(source.count(end), 1)
            return start + source.split(start, 1)[1].split(end, 1)[0]
        functions = span('function executionConstraints(', 'function admissionCell(') + '\n' + span(
            'function plannerGapModel(', 'async function loadParallelDeployment(')
        javascript = '\n'.join([
            'const PLANNER_LOT_SIZE=1,PLANNER_COMPACT_TARGET=4,PLANNER_EXECUTION_VENUE="saved";',
            'const fmt0=x=>String(x),fmt=x=>String(x),pct=x=>String(x),esc=x=>String(x);',
            'let currentPlannerSnapshot=null;',
            'const nodes={buyPlanBody:{innerHTML:""},plannerCash:{value:""}}, $=id=>nodes[id];',
            # These throw if the expected no-affordable-unit path changes.
            'const localStorage={getItem(){throw Error("unexpected storage read")},setItem(){throw Error("unexpected storage write")}};',
            'const fetch=()=>{throw Error("network forbidden")};',
            functions,
            'const data=' + json.dumps(data, ensure_ascii=True) + ';',
            'const results=[1000,10000].map(cash=>{nodes.plannerCash.value=String(cash);renderBuyPlan(data);return {cash,html:nodes.buyPlanBody.innerHTML,snapshot:currentPlannerSnapshot};});',
            'process.stdout.write(JSON.stringify(results));',
        ])
        result = subprocess.run(['node'], input=javascript, encoding='utf-8', capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        for rendered in json.loads(result.stdout):
            self.assertIn('当前有策略信号', rendered['html'])
            self.assertIn('MSFT 预算 $118 / 1股约 $498.43', rendered['html'])
            self.assertIn('战术通道不会把小额信号放大', rendered['html'])
            self.assertIsNone(rendered['snapshot'])
            self.assertNotIn('成交后填首次持仓', rendered['html'])


if __name__ == '__main__':
    unittest.main()
