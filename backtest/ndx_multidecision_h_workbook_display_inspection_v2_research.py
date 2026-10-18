"""Independent four-document to readable tables/chart data projection check."""
from copy import deepcopy
from fractions import Fraction
import json
import math


def require(condition, message):
    if not condition: raise ValueError(message)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def same(actual, expected):
    require(encoded(actual) == encoded(expected), 'Independent display projection mismatch')


def saved_text(value):
    if value is None or type(value) is str: return value
    if type(value) is dict and set(value) == {'numerator', 'denominator'}:
        return value['numerator'] + '/' + value['denominator']
    return encoded(value)


def displayed(value, percentage=False):
    if value is None: return None
    fraction = Fraction(saved_text(value))
    approximate = float(fraction)
    require(math.isfinite(approximate), 'Finite display-only value')
    if percentage: approximate *= 100
    return format(approximate, '.2f') + ('%' if percentage else '')


def inspect_display(*, display, presentation_document, supplement_document, diagnostics_document, chain_document, references):
    require(set(references) == {'presentation', 'supplement', 'diagnostics', 'chain'}, 'Four document identities')
    documents = (presentation_document, supplement_document, diagnostics_document, chain_document)
    schemas = ('MULTIDECISION_PATH_PRESENTATION_DOCUMENT_V1', 'MULTIDECISION_HOLDINGS_SUPPLEMENT_DOCUMENT_V1',
               'CANDIDATE_SAVED_RISK_DIAGNOSTIC_DOCUMENT_V1', 'MULTIDECISION_DAILY_CHAIN_DOCUMENT_V1')
    for document, schema in zip(documents, schemas): require(document['schema'] == schema, 'Source document role')
    presentation = presentation_document['presentation']; supplement = supplement_document['supplement']; chain = chain_document['projection']
    for body in (presentation, supplement, diagnostics_document, chain):
        require(body['point_in_time_verified'] is False and body['promotion_allowed'] is False, 'No acquired authority')
    same(chain['references'], {k: references[k] for k in ('supplement', 'diagnostics')})
    same(diagnostics_document['input_references']['inputs'], supplement['references']['candidate_inputs'])
    same(presentation_document['input_references']['candidate_inputs'], supplement['references']['candidate_inputs'])
    calendar = supplement['calendar']
    require(len(calendar) == 120 and calendar == sorted(set(calendar)), 'Original complete calendar')
    same(chain['calendar'], calendar)
    original_tables, saved_tables = presentation['tables'], supplement['tables']
    require(len(original_tables) == 11 and len(saved_tables) == 6 and len(chain['tables']) == 4, 'Original full table inventory')
    metric_rows = original_tables[1]['rows']; curve_rows = original_tables[5]['rows']; holding_rows = saved_tables[3]['rows']
    same([original_tables[1]['name'], original_tables[5]['name'], saved_tables[3]['name']], ['已存路径指标', '已存归一轨迹', '每日SID原持仓'])
    same([(r[0], r[4]) for r in metric_rows], [(i, role) for i in range(16) for role in ('候选', '原八只控制')])
    require(len(curve_rows) == 3120, 'All original 3120 curve points')
    same([(p['role'], p['track_index']) for p in chain['paths']], [(role, i) for role in ('candidate', 'control') for i in range(16)])
    same([p['track_index'] for p in diagnostics_document['paths']], [8, 10, 12, 14])
    diagnostics = {p['track_index']: p for p in diagnostics_document['paths']}
    last = {}
    for row in holding_rows:
        if row[5] == calendar[-1] and row[6] is not None:
            key = tuple(row[i] for i in (0, 1, 6)); require(key not in last, 'Unique final SID position'); last[key] = row
    role_keys = {'候选': 'candidate', '原八只控制': 'control'}
    basis_names = {'DERIVED_SUM_OF_SAVED_WHOLE_SID_WEIGHTS_NO_RENORMALIZATION': '原整股权重逐链相加，未重新归一',
                   'ORIGINAL_SAVED_CONTROL_CONTINUOUS_CHAIN_WEIGHTS': '原存控制连续链权重',
                   'PREVIOUSLY_AUDITED_CANDIDATE_CONTINUOUS_DERIVED_CHAIN_WEIGHTS': '已审候选连续派生链权重'}
    overview, positions = [], []
    for metric in metric_rows:
        index, mode, lane, track, label, status, cumulative, annual, drawdown = metric
        role = role_keys[label]; bundle = supplement['original_raw_bundles_preserved'][role][index]
        chain_path = chain['paths'][index + (16 if role == 'control' else 0)]
        if bundle is None:
            require(role == 'candidate' and index < 8 and status == 'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT' and chain_path['rows'] is None, 'Blocked position has no account')
            date_value, effective, chain_view = None, None, None
            holding_count = None
            stock_view, basis = '未执行：来源阻断', '来源阻断，未执行账户'
        else:
            require(status == 'SAVED_PATH_DIAGNOSTIC', 'Saved returned status')
            day = bundle['document']['result']['daily'][-1];date_value = day['session'];same(date_value, calendar[-1])
            quantities = day['shares'] if index % 2 else {sid: item['shares'] for sid, item in day['holdings'].items()}
            require(type(quantities) is dict and all(type(q) in (int, float) and math.isfinite(q) and q >= 0 for q in quantities.values()), 'Original nonnegative holding quantities')
            holding_count = sum(1 for q in quantities.values() if q > 0)
            chain_day = chain_path['rows'][-1];same(chain_day['session'], date_value);basis = chain_day['basis']
            chain_view = None if chain_day['chain_weights'] is None else '; '.join(name + '：' + displayed(value, True) for name, value in chain_day['chain_weights'].items())
            if role == 'candidate' and index % 2 == 0:
                diagnostic = diagnostics[index]['projection']['rows'][-1]['diagnostic'];same(diagnostic['session'], date_value)
                weights = diagnostic['security_weights'];effective = None if diagnostic['metrics'] is None else saved_text(diagnostic['metrics']['effective_n'])
            else:
                weights = day['risk'].get('actual_weights', {});effective = saved_text(day['risk'].get('effective_n'))
            labels = []
            for (holding_role, holding_index, sid), row in last.items():
                if holding_role != role or holding_index != index: continue
                weight = saved_text(weights.get(sid))
                labels.append(row[7] + '：' + ('原值未提供' if weight is None else displayed(weight, True)))
                positions.append([mode, lane, track, label, date_value, sid, row[7], row[8], row[10], weight, basis, row[11], row[12]])
            stock_view = '; '.join(labels) if labels else '空仓：股票权重与风险undefined'
        overview.append([mode, lane, track, label, status, date_value, holding_count, stock_view, displayed(cumulative, True), displayed(annual, True),
                         displayed(drawdown, True), displayed(effective), chain_view, basis_names.get(basis, basis),
                         '尚未晋级：缺独立cohort P50/P10/P90、正式逐项非劣比较及新前瞻OOS/PIT证据。'])
    tables = [dict(name='组合主视图', headers=['汇率模式', '目标类型', '账户轨', '角色', '原状态', '期末日期', '期末实际持仓数k', '期末真实股票及权重（展示近似）',
                                            '累计收益（展示近似）', '年化收益（展示近似）', '最大回撤（展示近似）', '期末有效N（展示近似）', '期末逐链权重（展示近似）', '链权重数值口径', '未晋级原因'], rows=overview),
              dict(name='期末真实股票比例', headers=['汇率模式', '目标类型', '账户轨', '角色', '日期', 'SID', '真实ticker', 'issuer', '原持仓数量文本', '股票权重精确原文', '权重数值口径', '身份来源', 'RAW来源'], rows=positions)]
    tables += deepcopy(original_tables + saved_tables)
    for source_table in chain['tables']:
        result = deepcopy(source_table)
        if result['name'] == '未执行阻断轨道': result['name'] = '链投影原阻断轨道'
        tables.append(result)
    daily_rows, weight_rows = [], []
    for path in diagnostics_document['paths']:
        for original in path['projection']['rows']:
            diagnostic = original['diagnostic']
            prefix = [path['track_index']] + path['coordinate'] + [diagnostic['session'], diagnostic['status']]
            numbers = [None if diagnostic['metrics'] is None else saved_text(diagnostic['metrics'][key])
                       for key in ('hhi', 'effective_n', 'top1_weight', 'top3_weight', 'minimum_single_weight', 'risk_chain_top1_weight')]
            daily_rows.append(prefix + numbers + [encoded(diagnostic['chain_weights']), encoded(original['source_locator_tokens'])])
            if not diagnostic['security_weights']: weight_rows.append(prefix + [None, None, None, None, encoded(original['source_locator_tokens'])])
            for sid, weight in diagnostic['security_weights'].items():
                observation = diagnostic['label_observations'][sid]
                weight_rows.append(prefix + [sid, saved_text(weight), observation['label'], observation['observation_session'], encoded(original['source_locator_tokens'][sid])])
    prefix = ['轨道序号', 'FX', 'lane', '账户轨', '日期', '原诊断状态']
    tables += [dict(name='候选连续派生每日风险', headers=prefix + ['HHI精确分数', '有效N精确分数', '最大单股精确分数', '前三股精确分数', '最小单股精确分数', '最大链精确分数', '链权重原值JSON', '来源'], rows=daily_rows),
               dict(name='候选连续派生SID权重', headers=prefix + ['SID', '权重精确分数', '风险链', '标签观察日', '来源'], rows=weight_rows)]
    series = {}
    for row in curve_rows: series.setdefault(tuple(row[:5]), []).append((row[5], row[6]))
    require(len(series) == 26, 'All twenty-six real series')
    for points in series.values(): same([p[0] for p in points], calendar)
    charts = []
    for index in range(16):
        mode, lane, track = metric_rows[index * 2][1:4]
        keys = [(index, mode, lane, track, role) for role in role_keys if (index, mode, lane, track, role) in series]
        keys.append((None, mode, None, None, '012922参考'))
        require(len(keys) == (2 if index < 8 else 3), 'Blocked candidate has no fabricated series')
        rows = [[session] + [float(Fraction(series[key][day][1])) for key in keys] for day, session in enumerate(calendar)]
        require(all(math.isfinite(v) for row in rows for v in row[1:]), 'Finite original fraction display conversion')
        charts.append(dict(name=f'曲线{index+1:02d}_{lane}_{track}', track_index=index,
                           title=f'{mode} · {lane} · {track}（近似图示）',
                           note='原已审归一净值精确分数转binary64，仅用于图示；不重算收益。' + ('候选来源阻断，未绘制候选曲线。' if index < 8 else ''),
                           headers=['日期'] + [key[4] + '（近似）' for key in keys], rows=rows, source_series_keys=[list(key) for key in keys]))
    expected = dict(schema='MULTIDECISION_H_WORKBOOK_DISPLAY_V2', tables=tables, charts=charts, references=deepcopy(references),
                    original_curve_row_count=3120, original_curve_series_count=26,
                    chart_conversion='BINARY64_APPROXIMATION_OF_SAVED_EXACT_FRACTIONS_FOR_DISPLAY_ONLY',
                    main_view_rounding='TWO_DECIMAL_DISPLAY_ONLY_ORIGINAL_VALUES_PRESERVED_IN_EXACT_TABLES',
                    financial_recomputation_performed=False, account_executed=False, point_in_time_verified=False, promotion_allowed=False, full_h_delivery_complete=False)
    same(display, expected)
    return dict(status='PASS_INDEPENDENT_READABLE_DISPLAY_MAPPING', table_count=len(tables), chart_count=16,
                original_curve_series_count=26, original_curve_row_count=3120, main_view_row_count=32,
                final_sid_row_count=len(positions), missing_paths_filled_with_zero=False, financial_recomputation_performed=False)


def chart_expectations(display):
    """Translate independently checked display coordinates into OOXML ranges."""
    charts = []
    for chart in display['charts']:
        name = chart['name'];quoted = "'" + name.replace("'", "''") + "'"
        series = []
        for column, label in enumerate(chart['headers'][1:], 2):
            letter = chr(64 + column)
            series.append(dict(name=label, categories_formula=quoted + '!$A$5:$A$124',
                               values_formula=quoted + f'!${letter}$5:${letter}$124',
                               categories=[row[0] for row in chart['rows']], values=[row[column - 1] for row in chart['rows']]))
        charts.append(dict(sheet_name=name, title=chart['title'], series=series))
    return charts
