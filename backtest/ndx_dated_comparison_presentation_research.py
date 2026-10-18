"""Chinese display tables for saved comparison summaries; no financial recomputation.

This pure adapter does not authenticate source bytes. A publishing consumer must
verify the summary and its independent audit before using these tables.
"""
from fractions import Fraction
import math


FULL = 6222659648236112670
TRACKS = {
    'candidate_integer': '候选整数账户',
    'incumbent_integer': '原组合整数账户',
    'candidate_continuous': '候选连续权重',
    'incumbent_continuous': '原组合连续权重',
}
MODES = {
    'STRICT_SAME_SESSION_FX': '严格同日汇率',
    'BACKWARD_LATEST_VALID_FX': '向前取最近有效汇率',
}
SPECS = {
    'equal_weight': '等权',
    'constrained_fixed_shrinkage': '约束收缩权重',
    'constrained_fixed_shrinkage_turnover_anchor': '约束收缩与换手锚权重',
}
STATUS = {
    'AUDITED_COMPARISON_PRESENT': '已有独审比较',
    'NOT_SUPPLIED': '未提供比较',
    'AVAILABLE': '已有路径',
    'NOT_EXECUTED_NONPOSITIVE_TARGET': '存在零目标，整数账户未执行',
    'TECHNICAL_MISSING': '技术原因缺失',
    'FROZEN': '目标已冻结',
    'NO_PLAN': '无交易计划',
    'FILLED': '已成交',
    'REJECTED': '已拒单',
    'CANCELLED_SPLIT': '因拆股撤销',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def display_metric(metric):
    """Convert an already saved exact ratio only for Excel numeric display."""
    if metric is None:
        return None
    exact = metric['exact']
    require(type(exact) is str, 'Exact metric must be a string')
    fraction = Fraction(exact)
    require(str(fraction) == exact, 'Noncanonical exact metric')
    value = float(fraction)
    require(math.isfinite(value), 'Unrepresentable display metric')
    return value


def build_tables(summary):
    require(summary['schema'] == 'DATED_COMPARISON_RESULTS_TABLES_V1', 'Summary schema')
    require(type(summary['materialized_task_count']) is int and summary['materialized_task_count'] == 1632, 'Full task denominator')
    require(type(summary['full_new_cutoff_task_denominator']) is int and summary['full_new_cutoff_task_denominator'] == FULL, 'Full domain')
    for key in ('formal_comparison_passed', 'point_in_time_verified', 'promotion_allowed', 'winner_selected', 'future_independent_oos', 'cohort_statistics_computed'):
        require(summary[key] is False, 'Historical diagnostic authority: ' + key)
    require(summary['mode_order'] == list(MODES), 'Separate ordered FX modes')
    rows = summary['rows']
    require(len(rows) == 1632 and len({row['numerical_task_id'] for row in rows}) == 1632, 'Full unique task rows')
    task_rows, metric_rows, distance_rows, weight_rows = [], [], [], []
    present = 0
    for ordinal, row in enumerate(rows, 1):
        identifier = row['numerical_task_id']
        state = row['status']
        require(state in ('NOT_SUPPLIED', 'AUDITED_COMPARISON_PRESENT'), 'Task status')
        task_rows.append([ordinal, identifier, row['k'], SPECS[row['weight_spec']], STATUS[state]])
        if state == 'NOT_SUPPLIED':
            require(row['tracks'] is None and row['original_targets'] is None and row['nav_modes'] is None, 'Missing comparison has no invented values')
            continue
        present += 1
        require(set(row['tracks']) == set(TRACKS) and set(row['nav_modes']) == set(MODES), 'All tracks and FX modes')
        require(len(row['original_targets']) == row['k'], 'All target slots')
        for position in row['original_targets']:
            weight = position['target_weight']
            require(type(weight) in (float, int) and math.isfinite(weight) and weight >= 0, 'Original nonnegative weight')
            weight_rows.append([ordinal, identifier, position['ticker'], position['security_id'], position['issuer_id'], weight])
        for code, label in TRACKS.items():
            track = row['tracks'][code]
            available = track['status'] == 'AVAILABLE'
            require(available == (track['metrics'] is not None), 'Missing metrics cannot become zero')
            values = [display_metric(track['metrics'][key]) if available else None for key in ('cumulative_return', 'annualized_return', 'maximum_drawdown')]
            decision = track['decision_status']
            executions = track['execution_statuses']
            metric_rows.append([ordinal, label, STATUS[track['status']], STATUS[decision] if decision is not None else '不适用', '、'.join(STATUS[x] for x in executions) if executions else '无执行记录', *values])
        for mode, mode_label in MODES.items():
            saved = row['nav_modes'][mode]
            for kind, kind_label in (('integer', '整数账户'), ('continuous', '连续权重')):
                for metric, metric_label in (('annualized_return', '年化收益'), ('maximum_drawdown', '最大回撤')):
                    distances = saved['absolute_distance_comparisons'][kind][metric]
                    distance_rows.append([ordinal, mode_label, kind_label, metric_label, display_metric(saved['nav_metrics'][metric]), display_metric(distances['candidate_absolute_distance']), display_metric(distances['incumbent_absolute_distance']), display_metric(distances['candidate_minus_incumbent_distance'])])
    require(type(summary['supplied_comparison_count']) is int and summary['supplied_comparison_count'] == present, 'Present count')
    require(type(summary['not_supplied_count']) is int and summary['not_supplied_count'] == 1632-present, 'Missing count')
    overview = [
        ['固定队列任务数', 1632], ['已有独审比较', present], ['未提供比较', 1632-present],
        ['完整组合域任务数（精确文本）', str(FULL)],
        ['完整域未在本比较汇总中体现（精确文本）', str(FULL-present)],
        ['研究窗口', '2026-03-20 至 2026-09-21；127 个估值点、126 个收益间隔'],
        ['适用范围', '条件历史单路径诊断；不代表正式 cohort 包络或独立未来 OOS'],
        ['差值方向', '候选到 012922 的绝对距离减原组合绝对距离；负值表示更接近参考'],
        ['空值含义', '缺失或不适用，不等于零；实际零值保留'],
        ['展示精度', '比例以数值展示；原始精确分数及来源以已封 JSON 为准'],
        ['权重语义', '原始目标权重逐项保留，不在展示层归一化'],
        ['当前展示范围', '任务、指标、双汇率距离及目标权重；不包含账户日曲线或正式晋级结论'],
    ]
    tables = [
        dict(name='研究概览', headers=['项目', '内容'], rows=overview, percentage_columns=[]),
        dict(name='全部任务', headers=['序号', '任务 ID', '持仓槽位 k', '权重规格', '比较状态'], rows=task_rows, percentage_columns=[]),
        dict(name='四轨指标', headers=['任务序号', '路径', '路径状态', '决策状态', '执行状态', '累计收益', '年化收益', '最大回撤'], rows=metric_rows, percentage_columns=[5, 6, 7]),
        dict(name='双基准距离', headers=['任务序号', '汇率口径', '路径口径', '指标', '012922 指标', '候选绝对距离', '原组合绝对距离', '候选减原组合距离'], rows=distance_rows, percentage_columns=[4, 5, 6, 7]),
        dict(name='原始目标权重', headers=['任务序号', '任务 ID', 'Ticker', '证券 ID', '发行人 ID', '原始权重'], rows=weight_rows, percentage_columns=[5]),
    ]
    return dict(schema='DATED_COMPARISON_CHINESE_DISPLAY_TABLES_V1', tables=tables, source_bytes_authenticated=False, economics_recomputed=False, formal_comparison_passed=False, future_independent_oos=False)
