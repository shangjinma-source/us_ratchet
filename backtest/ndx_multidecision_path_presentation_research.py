"""Pure Chinese projection of saved K evidence. No IO or financial recomputation.

Reference equality is structural only. A source wrapper must authenticate original
bytes and inventories before and after calling this module and after publishing.
All metric strings remain text; annualization is the original Decimal diagnostic.
"""
from copy import deepcopy
import json
import math
import re


MODES = {'STRICT_SAME_SESSION_FX': '严格同日汇率',
         'BACKWARD_LATEST_VALID_FX': '向前取最近有效汇率'}
LANES = {'RETURN': '收益', 'BAD_TAIL': '尾部', 'DRAWDOWN': '回撤',
         'TARGET_ENVELOPE': '目标包络'}
TRACKS = {'CONTINUOUS': '连续权重', 'WHOLE_LOT': '整股'}
FLAGS = ('account_executed', 'fit_performed', 'cohort_statistics_computed',
         'formal_comparison_passed', 'formal_noninferiority_passed',
         'future_independent_oos', 'point_in_time_verified', 'promotion_allowed',
         'source_bytes_authenticated', 'winner_selected')
MISSING = ['INDEPENDENT_COHORT_P50_P10_P90',
           'FORMAL_COMPONENTWISE_NONINFERIORITY', 'FRESH_FORWARD_OOS_AND_PIT']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def exact(left, right, message):
    require(encoded(left) == encoded(right), message)


def false(document, keys):
    for key in keys:
        require(document.get(key) is False, 'Diagnostic authority: ' + key)


def ratio_text(value):
    require(type(value) is dict and set(value) == {'numerator', 'denominator'}, 'Saved ratio')
    require(type(value['numerator']) is str and re.fullmatch(r'-?(0|[1-9][0-9]*)', value['numerator']), 'Numerator text')
    require(type(value['denominator']) is str and re.fullmatch(r'[1-9][0-9]*', value['denominator']), 'Denominator text')
    return value['numerator'] + '/' + value['denominator']


def metric_cells(metrics, calendar):
    if metrics is None:
        return [None, None, None]
    require(type(metrics['observation_count']) is int and metrics['observation_count'] == len(calendar), 'Metric calendar count')
    exact([row['session'] for row in metrics['wealth']], calendar, 'No shortened metric curve')
    require(type(metrics['annualized_return_diagnostic_decimal']) is str, 'Saved Decimal text')
    return [ratio_text(metrics['cumulative_return']),
            metrics['annualized_return_diagnostic_decimal'], ratio_text(metrics['maximum_drawdown'])]


def table(name, headers, rows):
    # Strings must be written as literal text, never interpreted as Excel formulas.
    return dict(name=name, headers=headers, rows=rows, all_cells_literal=True,
                financial_numeric_conversion_performed=False)


def additional_tables(inputs, comparison, references, dates):
    targets, risks, exposures = [], [], []
    for lane_index, lane in enumerate(inputs['rows']):
        schedule = lane['original_targets_schedule']
        by_date = {entry['decision_date']: entry for entry in schedule}
        require(len(by_date) == len(schedule) and set(by_date) <= set(dates), 'Unique original target dates')
        for date_index, date in enumerate(dates):
            coordinate_index = date_index * 8 + lane_index
            prefix = [coordinate_index, date, MODES[lane['fx_mode']], LANES[lane['lane']]]
            pointer = dict(references['candidate_inputs'], json_pointer=f'/inputs/rows/{lane_index}/original_targets_schedule')
            if date not in by_date:
                targets.append(prefix + ['原目标未提供', None, None, None, None, None, None, encoded(pointer)])
                continue
            entry = by_date[date]
            require(type(entry['targets']) is dict and bool(entry['targets']), 'Original nonempty targets')
            chain_maps = [track['stateful_input']['risk_chains_by_decision'].get(date, {}) for track in lane['tracks']]
            exact(chain_maps[0], chain_maps[1], 'Same saved target risk labels in both tracks')
            for sid, target in entry['targets'].items():
                require(type(target['ticker']) is str and bool(target['ticker']) and not target['ticker'].startswith('SID_COLUMN_'), 'Original display ticker')
                weight = target['target_weight']
                require(type(weight) in (int, float) and math.isfinite(weight) and weight >= 0, 'Original nonnegative target weight')
                targets.append(prefix + ['已保存原目标', sid, target['ticker'], target['issuer_id'], encoded(weight), entry['execution_date'], chain_maps[0].get(sid), encoded(pointer)])
    for index, row in enumerate(comparison['rows']):
        mode, lane, track = row['coordinate']
        for role, label in (('candidate', '候选'), ('control', '原八只控制')):
            saved = row[role]
            diagnostics = saved.get('saved_execution_diagnostics', {})
            key = 'decisions' if track == 'WHOLE_LOT' else 'rebalances'
            records = diagnostics.get(key, [])
            by_date = {entry['decision_date']: (ordinal, entry) for ordinal, entry in enumerate(records)}
            require(len(by_date) == len(records) and set(by_date) <= set(dates), 'Unique saved decision risk dates')
            for date in dates:
                prefix = [index, MODES[mode], LANES[lane], TRACKS[track], label, date]
                pointer = dict(references['comparison'], json_pointer=f'/comparison/rows/{index}/{role}')
                if date not in by_date:
                    risks.append(prefix + ['原决策记录未提供', None, None, encoded(pointer)])
                    continue
                ordinal, decision = by_date[date]
                pointer['json_pointer'] += f'/saved_execution_diagnostics/{key}/{ordinal}'
                risk = decision.get('decision_risk')
                risks.append(prefix + ['已保存决策风险' if risk is not None else '原决策未保存风险数值', encoded(risk) if risk is not None else None, encoded(decision), encoded(pointer)])
                if risk is None:
                    continue
                for sid, weight in risk['actual_weights'].items():
                    exposures.append(prefix + [sid, encoded(weight), decision.get('risk_chains', {}).get(sid), decision.get('risk_chain_observation_dates', {}).get(sid), encoded(pointer)])
    return [table('候选原目标证券', ['原坐标', '决策日期', '汇率模式', '目标lane', '状态', 'SID', '真实ticker', 'issuer', '原目标权重文本', '执行日期', '原风险链标签', '来源JSON'], targets),
            table('已保存决策风险', ['轨道序号', '汇率模式', '目标lane', '账户轨', '角色', '决策日期', '状态', '原风险JSON', '完整原决策JSON', '来源JSON'], risks),
            table('决策逐SID原暴露', ['轨道序号', '汇率模式', '目标lane', '账户轨', '角色', '决策日期', 'SID', '原实际权重文本', '原风险链标签', '标签观察日期', '来源JSON'], exposures)]


def build_tables(*, comparison_document, publication, audit, candidate_inputs_document, references):
    """Validate saved structural bindings then project all rows without executing IO."""
    require(set(references) == {'comparison', 'publication', 'audit', 'reader', 'candidate_inputs'}, 'Five explicit source references')
    for reference in references.values():
        require(set(reference) == {'path', 'sha256'} and type(reference['path']) is str and bool(reference['path']), 'File reference')
        require(type(reference['sha256']) is str and re.fullmatch('[0-9a-f]{64}', reference['sha256']), 'Reference SHA')
    require(comparison_document['schema'] == 'MULTIDECISION_PATH_COMPARISON_DOCUMENT_V1', 'K document schema')
    require(publication['schema'] == 'MULTIDECISION_PATH_COMPARISON_PUBLICATION_V1', 'K publication schema')
    require(audit['schema'] == 'MULTIDECISION_PATH_COMPARISON_INDEPENDENT_READBACK_V1' and audit['status'] == 'PASS', 'K independent PASS required')
    require(audit['scope'] == 'SAVED16_FULL_PATH_METRICS_AND_PAIRED_DISTANCES_NOT_ACCOUNT_REAUDIT_OR_COHORT_GATE', 'K audit scope')
    exact(publication['comparison_reference'], references['comparison'], 'Published comparison')
    exact(audit['comparison_reference'], references['comparison'], 'Audited comparison')
    exact(audit['publication_reference'], references['publication'], 'Audited publication')
    require(audit['reader_sha256'] == references['reader']['sha256'], 'Reader binding')
    for document in (comparison_document, publication, audit):
        false(document, ('formal_comparison_passed', 'formal_noninferiority_passed', 'future_independent_oos', 'point_in_time_verified', 'promotion_allowed', 'fit_performed', 'cohort_statistics_computed'))
    exact(publication['source_hashes'], comparison_document['source_hashes'], 'Producer source closure')
    exact(audit['input_references'], comparison_document['input_references'], 'Audited input roles')
    exact(publication['input_references'], comparison_document['input_references'], 'Published input roles')
    exact(comparison_document['input_references']['candidate_inputs'], references['candidate_inputs'], 'Decision source binding')
    require(candidate_inputs_document['schema'] == 'MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1', 'Decision input schema')
    comparison = comparison_document['comparison']
    require(comparison['schema'] == 'MULTIDECISION_SAME_WINDOW_PATH_DIAGNOSTIC_V1', 'Comparison schema')
    false(comparison, FLAGS)
    exact(comparison['missing_formal_evidence'], MISSING, 'Original missing formal evidence')
    for body in (comparison, candidate_inputs_document['inputs'], audit['inspection']):
        for key, count in (('coordinate_count', 48), ('lane_count', 8), ('track_count', 16)):
            require(type(body[key]) is int and body[key] == count, 'Complete domain: ' + key)
    inputs = candidate_inputs_document['inputs']
    coordinates = inputs['outer_coordinate_rows_preserved']
    require(len(coordinates) == 48 and len(inputs['rows']) == 8, 'All decision positions and lanes')
    dates = [row['coordinate'][0] for row in coordinates[::8]]
    require(len(set(dates)) == 6 and dates == sorted(dates), 'Six ordered decision dates')
    expected = [[date, mode, lane] for date in dates for mode in MODES for lane in LANES]
    exact([row['coordinate'] for row in coordinates], expected, 'Original 48 coordinate order')
    for index, row in enumerate(coordinates):
        require(type(row['coordinate_index']) is int and row['coordinate_index'] == index, 'Original coordinate index')
    rows = comparison['rows']
    exact([row['coordinate'] for row in rows], [[mode, lane, track] for mode in MODES for lane in LANES for track in TRACKS], 'All ordered 16 tracks')
    calendar = comparison['calendar']
    require(len(calendar) == 120 and len(set(calendar)) == 120 and calendar == sorted(calendar), 'Full original calendar')
    nav = comparison['nav_modes_preserved']
    require(set(nav['modes']) == set(MODES), 'Both original FX modes')
    false(nav, ('promotion_allowed', 'point_in_time_verified', 'formal_comparison_passed', 'future_independent_oos', 'cohort_statistics_computed'))
    overview, metrics, distances, curves = [], [], [], []
    for index, row in enumerate(rows):
        require(type(row['track_index']) is int and row['track_index'] == index, 'Track index')
        false(row, FLAGS)
        mode, lane, track = row['coordinate']
        require(row['nav_mode'] == mode, 'Matching NAV mode')
        prepared = inputs['rows'][index // 2]
        exact([prepared['fx_mode'], prepared['lane']], [mode, lane], 'Prepared lane order')
        exact(prepared['coordinate_indexes'], list(range(index // 2, 48, 8)), 'Six decision positions per lane')
        exact(row['prepared_blocking_reasons']['candidate'], prepared['tracks'][index % 2]['blocking_reasons'], 'Original candidate blockers')
        labels = [index, MODES[mode], LANES[lane], TRACKS[track]]
        overview.append(labels + [row['candidate']['status'], row['control']['status'], encoded(row['prepared_blocking_reasons']), row['candidate']['reason'], row['control']['reason']])
        for role, label in (('candidate', '候选'), ('control', '原八只控制')):
            saved = row[role]
            require(saved['status'] in ('SAVED_PATH_DIAGNOSTIC', 'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT'), 'Saved path status')
            require((saved['metrics'] is None) == (saved['status'] == 'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT'), 'Blocked path has no metric')
            metrics.append(labels + [label, saved['status']] + metric_cells(saved['metrics'], calendar))
            if saved['metrics'] is not None:
                curves.extend(labels + [label, value['session'], ratio_text(value['normalized_wealth'])] for value in saved['metrics']['wealth'])
        saved_distances = row['distances']
        distance_cells = []
        for role in ('candidate', 'control'):
            value = saved_distances[role]
            distance_cells.extend([None, None] if value is None else [value['annualized_return_absolute_distance'], value['maximum_drawdown_absolute_distance']])
        difference = saved_distances['candidate_minus_control_absolute_distance']
        distance_cells.extend([None, None] if difference is None else [difference['annualized_return'], difference['maximum_drawdown']])
        require(all(value is None or type(value) is str for value in distance_cells), 'Original distance strings')
        distances.append(labels + distance_cells + [encoded(saved_distances)])
    nav_rows = []
    for mode in MODES:
        saved = nav['modes'][mode]
        require(saved['mode'] == mode, 'NAV mode identity')
        nav_rows.append([MODES[mode], saved['status'], encoded(saved['missing_sessions'])] + metric_cells(saved['metrics'], calendar))
        if saved['metrics'] is not None:
            curves.extend([None, MODES[mode], None, None, '012922参考', value['session'], ratio_text(value['normalized_wealth'])] for value in saved['metrics']['wealth'])
    tables = [table('轨道与阻断', ['轨道序号', '汇率模式', '目标lane', '账户轨', '候选状态', '控制状态', '原阻断JSON', '候选原因', '控制原因'], overview),
              table('已存路径指标', ['轨道序号', '汇率模式', '目标lane', '账户轨', '角色', '状态', '累计收益精确分数', '年化收益原Decimal文本', '最大回撤精确分数'], metrics),
              table('到NAV的逐项距离', ['轨道序号', '汇率模式', '目标lane', '账户轨', '候选年化绝对距离', '候选回撤绝对距离', '控制年化绝对距离', '控制回撤绝对距离', '年化距离候选减控制', '回撤距离候选减控制', '原距离JSON'], distances),
              table('两种NAV参考', ['汇率模式', '状态', '原缺失日期JSON', '累计收益精确分数', '年化收益原Decimal文本', '最大回撤精确分数'], nav_rows),
              table('48个决策位置', ['原序号', '日期', '汇率模式', '目标lane', '原状态', '完整原证据JSON'], [[i, r['coordinate'][0], MODES[r['coordinate'][1]], LANES[r['coordinate'][2]], r['status'], encoded(r)] for i, r in enumerate(coordinates)]),
              table('已存归一轨迹', ['轨道序号', '汇率模式', '目标lane', '账户轨', '角色', '日期', '归一净值精确分数'], curves),
              table('来源索引', ['角色', '路径', 'SHA256'], [[key, value['path'], value['sha256']] for key, value in references.items()]),
              table('范围与未晋级', ['项目', '原文'], [['范围', comparison['scope']], ['缺失正式证据', encoded(MISSING)], ['NAV原限制', encoded(nav['original_alignment_limitations'])], ['FX原语义', encoded(nav['original_fx_context'])], ['数值口径', '已存binary64路径的精确分数与原Decimal80年化诊断；不是精确经济值或正式cohort统计']])]
    tables.extend(additional_tables(inputs, comparison, references, dates))
    remaining = ['CONTROL_REAL_TICKER_AND_ORIGINAL_TARGET_DISPLAY_REQUIRES_CONTROL_INPUTS', 'FULL_DAILY_SID_HOLDINGS_AND_RISK_REQUIRES_EXECUTION_RAW_CLOSURE', 'CONTINUOUS_SID_AND_CHAIN_EXPOSURE_NOT_SAVED_REQUIRES_SEPARATE_DERIVATION', 'FULL_CHAIN_AGGREGATES_NOT_COMPUTED', 'WORKBOOK_CELL_READBACK_AND_VISUAL_ACCEPTANCE']
    tables[-4]['rows'].append(['本阶段尚缺', encoded(remaining)])
    return dict(schema='MULTIDECISION_PATH_CHINESE_PRESENTATION_V1', scope='PURE_SAVED_EVIDENCE_PROJECTION_NOT_SOURCE_AUTHENTICATION', coordinate_count=48, lane_count=8, track_count=16, tables=tables,
                original_comparison_preserved=deepcopy(comparison), original_coordinates_preserved=deepcopy(coordinates), references=deepcopy(references),
                remaining_delivery_gaps=remaining, full_h_delivery_complete=False, financial_recomputation_performed=False, actual_publication_performed=False, **dict.fromkeys(FLAGS, False))
