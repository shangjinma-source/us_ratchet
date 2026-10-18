"""Exercise actual dashboard JavaScript with isolated signals and API responses."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node required")
class CashSignalRefreshTests(unittest.TestCase):
    def run_javascript(self, body):
        source = (ROOT / "web/index.html").read_text(encoding="utf-8")

        def span(start, end):
            return start + source.split(start, 1)[1].split(end, 1)[0]

        functions = "\n".join([
            span("function executionConstraints(", "function admissionCell("),
            span("function plannerGapModel(", "async function loadParallelDeployment("),
            span("async function refreshBuyPlan(", "function plannerRowNote("),
            span("function plannerRowNote(", "function currentMarketDate("),
            span("async function requestPlannerState(", "function plannerInputChanged("),
        ])
        script = "\n".join([
            'const PLANNER_LOT_SIZE=1,PLANNER_COMPACT_TARGET=4,PLANNER_EXECUTION_VENUE="test";',
            'const fmt0=x=>String(x),fmt=x=>String(x),pct=x=>String(x),esc=x=>String(x);',
            'let currentPlannerSnapshot=null,stateData=null,apiGet,stateRequestSequence=0;',
            'const nodes={buyPlanBody:{innerHTML:""},plannerCash:{value:"1000"},btnRefreshBuyPlan:{}};',
            'const $=id=>nodes[id]; const currentMarketDate=()=>"2026-10-08";',
            'const storage=new Map();const localStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)};',
            'const PLANNER_RECENT_KEY="recent";',
            'let briefCalls=0,executionCalls=0;const renderExecutiveBrief=()=>briefCalls++;const renderExecution=()=>executionCalls++;',
            functions,
            'const data={initialized:true,as_of:"2026-10-08",execution:{items:[{ticker:"AAA",side:"BUY",source:"tactical_limit",action:"BUY_NOW",amount:500,limit:100,live_price:99}]},execution_constraints:{lot_size:1,allow_fractional:false,fee_bps:10,min_fee:2,buy_plan_compact_target:4},account_readiness:{position_gaps:{account_fingerprint:"fixture",rows:[{ticker:"AAA",gap_amount:800,gap_ratio:0.8,gap_rank:1,position_kind:"real_position",target_amount:1000,real_market_value:200}]}},symbols:[]};',
            '(async()=>{' + body + '})().catch(error=>{console.error(error);process.exitCode=1;});',
        ])
        result = subprocess.run(["node"], input=script, text=True, encoding="utf-8",
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_funded_signal_allocates_real_whole_shares_with_fees(self):
        result = self.run_javascript('renderBuyPlan(data);process.stdout.write(JSON.stringify({rows:currentPlannerSnapshot.rows,html:nodes.buyPlanBody.innerHTML}));')
        row = result["rows"][0]
        self.assertEqual(row["shares"], 4)
        self.assertEqual(row["amount"], 402)
        self.assertLessEqual(row["notional"], 500)
        self.assertIn("已触价", result["html"])

    def test_cash_budget_gap_and_closed_position_have_distinct_reasons(self):
        result = self.run_javascript('''
            const outputs=[];
            for (const [cash,budget,gap,kind] of [[50,500,800,"real_position"],[1000,50,800,"real_position"],[1000,500,50,"real_position"],[1000,500,800,"reported_closed"]]) {
                data.execution.items[0].amount=budget;
                Object.assign(data.account_readiness.position_gaps.rows[0],{gap_amount:gap,position_kind:kind});
                outputs.push(plannerSignalDiagnostics(data,cash)[0]);
            }
            process.stdout.write(JSON.stringify(outputs));''')
        self.assertIn("本次现金", " ".join(result[0]["reasons"]))
        self.assertIn("策略预算", " ".join(result[1]["reasons"]))
        self.assertIn("真实缺口", " ".join(result[2]["reasons"]))
        self.assertIn("已报告清仓", " ".join(result[3]["reasons"]))

    def test_wait_has_current_limit_and_market_reason(self):
        result = self.run_javascript('''
            data.execution.items=[];
            data.symbols=[{ticker:"AAA",tactical:{action:"WAIT",amount:0,limit:80,live_price:99,text:"熊市预算为零"}}];
            process.stdout.write(JSON.stringify(plannerSignalDiagnostics(data,1000)[0]));''')
        self.assertEqual(result["price"], 80)
        self.assertIn("熊市预算为零", result["reasons"])

    def test_refresh_fetches_new_api_signal_instead_of_repainting_old_state(self):
        result = self.run_javascript('''
            stateData={execution:{items:[]}};
            const requests=[];apiGet=async path=>{requests.push(path);return data;};
            await refreshBuyPlan();
            process.stdout.write(JSON.stringify({requests,rows:currentPlannerSnapshot.rows,briefCalls,executionCalls,disabled:nodes.btnRefreshBuyPlan.disabled}));''')
        self.assertEqual(result["requests"], ["/api/state"])
        self.assertEqual(result["rows"][0]["shares"], 4)
        self.assertEqual((result["briefCalls"], result["executionCalls"]), (1, 1))
        self.assertFalse(result["disabled"])

    def test_failed_refresh_removes_current_execution_display(self):
        result = self.run_javascript('''
            currentPlannerSnapshot={rows:[{shares:5}]};
            apiGet=async()=>{throw Error("offline");};
            await refreshBuyPlan();
            process.stdout.write(JSON.stringify({snapshot:currentPlannerSnapshot,html:nodes.buyPlanBody.innerHTML,disabled:nodes.btnRefreshBuyPlan.disabled}));''')
        self.assertIsNone(result["snapshot"])
        self.assertIn("策略刷新失败", result["html"])
        self.assertFalse(result["disabled"])

    def test_same_day_disappeared_signal_does_not_resurrect_saved_shares(self):
        result = self.run_javascript('''
            renderBuyPlan(data);
            data.execution.items=[];
            renderBuyPlan(data);
            process.stdout.write(JSON.stringify({snapshot:currentPlannerSnapshot,html:nodes.buyPlanBody.innerHTML}));''')
        self.assertIsNone(result["snapshot"])
        self.assertIn("旧股数不再作为本次可执行清单", result["html"])

    def test_failed_refresh_then_cash_edit_cannot_revive_old_signals(self):
        result = self.run_javascript('''
            stateData=data;renderBuyPlan(stateData);
            apiGet=async()=>{throw Error("offline");};await refreshBuyPlan();
            nodes.plannerCash.value="2000";renderBuyPlan(stateData);
            process.stdout.write(JSON.stringify({snapshot:currentPlannerSnapshot,html:nodes.buyPlanBody.innerHTML}));''')
        self.assertIsNone(result["snapshot"])
        self.assertIn("修改现金不会恢复旧信号", result["html"])

    def test_delayed_old_auto_refresh_cannot_replace_manual_response(self):
        result = self.run_javascript('''
            let oldResolve;let calls=0;
            apiGet=()=>++calls===1?new Promise(resolve=>oldResolve=resolve):Promise.resolve(data);
            const oldRequest=requestPlannerState();
            await refreshBuyPlan();oldResolve({initialized:false});await oldRequest;
            process.stdout.write(JSON.stringify({initialized:stateData.initialized,shares:currentPlannerSnapshot.rows[0].shares}));''')
        self.assertTrue(result["initialized"])
        self.assertEqual(result["shares"], 4)

    def test_stale_bars_and_preview_state_are_visible(self):
        result = self.run_javascript('''
            data.latest_closed_session_date="2026-10-07";
            data.daily_bar_freshness={common_risk_daily_bar_date:"2026-10-06"};
            data.state_freshness={status:"DAILY_UPDATE_REQUIRED",state_last_run_date:"2026-07-30"};
            renderBuyPlan(data);
            process.stdout.write(JSON.stringify(nodes.buyPlanBody.innerHTML));''')
        self.assertIn("日线陈旧", result)
        self.assertIn("策略状态为预览", result)


if __name__ == "__main__":
    unittest.main()
