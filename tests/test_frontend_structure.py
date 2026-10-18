from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendStructureTests(unittest.TestCase):
    def test_today_page_has_one_authoritative_execution_plan(self):
        source = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertNotIn('id="panelBuyPlan"', source)
        self.assertNotIn("todayActions.slice(0, 3)", source)
        self.assertEqual(source.count("今日执行计划"), 3)
        self.assertIn("策略信号审计明细（非股数草案）", source)
        self.assertIn(
            "today: ['panelExecutiveBrief', 'panelMarket', 'panelConfigHealth']",
            source,
        )
        panel_start = source.index('<div class="card" id="panelExecutiveBrief">')
        panel_end = source.index("<!-- Panel: Config Health -->", panel_start)
        panel = source[panel_start:panel_end]

        self.assertIn('id="briefBody"', panel)
        self.assertIn('id="plannerCash"', panel)
        self.assertIn('id="plannerBrokerConfirmed"', panel)
        self.assertIn('id="buyPlanBody"', panel)
        self.assertIn('id="scheduledDeploymentBody"', panel)
        self.assertIn("唯一股数草案 · 不自动下单", panel)

    def test_scheduled_deployment_is_explicitly_separate_from_tactical_signal(self):
        source = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn("/api/parallel_deployment?", source)
        self.assertIn("本草案不等待战术信号", source)
        self.assertNotIn('id="plannerMinTransactions"', source)
        self.assertNotIn('id="plannerReviewSessions"', source)
        self.assertIn("券商交易考核未进入策略", source)
        self.assertIn("portfolio_optimization 动态 k 主轨继续独立运行", source)
        self.assertIn("migration_control 未进入本草案", source)
        self.assertIn("草案 ID：", source)
        self.assertIn("position.position_kind === 'reported_closed'", source)
        self.assertIn("等待新入场信号，不机械回补", source)

    def test_planner_cash_is_scoped_to_market_session(self):
        source = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn("const PLANNER_CASH_KEY = 'ratchet_planner_cash_v2'", source)
        self.assertIn("session_date: plannerSnapshotMarketDate()", source)
        self.assertIn("saved.session_date === sessionDate", source)
        self.assertIn("saved.source === 'manual'", source)
        self.assertIn("let selectedSource = 'session_default'", source)
        self.assertIn("selectedSource = 'broker_snapshot'", source)
        self.assertIn("selectedSource = 'manual'", source)
        self.assertIn("source: selectedSource", source)
        self.assertIn("source: 'manual'", source)
        self.assertIn("savedUpdatedAt >= brokerUpdatedAt", source)
        self.assertIn("updated_at: Date.now()", source)
        self.assertIn("broker.positions_confirmed_session_date === sessionDate", source)
        self.assertIn("broker.deployable_cash_persistence === 'until_user_update'", source)
        self.assertNotIn("localStorage.getItem('ratchet_planner_cash')", source)
        self.assertLess(
            source.index("stateData = await apiGet('/api/state')"),
            source.index("loadPlannerPrefs();", source.index("async function loadState()")),
        )

    def test_frontend_warns_when_signal_bars_lag_quote_session(self):
        source = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn("DAILY_BARS_LAG_QUOTE_SESSION", source)
        self.assertIn("今日战术结论可能仍基于上一完整日线", source)

    def test_tactical_planner_never_expands_signal_budget_to_available_cash(self):
        source = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn("unitNotional <= signalBudget + 0.01", source)
        self.assertIn("notional > signalBudget + 0.01", source)
        self.assertIn("Math.max(0, Number(row.item.amount || 0))", source)
        self.assertIn("战术通道不会把小额信号放大为按全部现金补仓", source)
        self.assertIn("recent.version === 3", source)


if __name__ == "__main__":
    unittest.main()
