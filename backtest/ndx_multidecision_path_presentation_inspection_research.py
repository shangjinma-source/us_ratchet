"""Independent saved-field presentation inspection; no producer imports or IO.

Checks display projection, not account arithmetic, source bytes, or H completion.
The source reader must authenticate all supplied documents before using this API.
"""
import json
import re

FX = ('STRICT_SAME_SESSION_FX', 'BACKWARD_LATEST_VALID_FX')
FX_LABEL = ('严格同日汇率', '向前取最近有效汇率')
OBJECTIVES = ('RETURN', 'BAD_TAIL', 'DRAWDOWN', 'TARGET_ENVELOPE')
OBJECTIVE_LABEL = ('收益', '尾部', '回撤', '目标包络')
ACCOUNT_LABEL = ('连续权重', '整股')
AUTHORITY = ('account_executed', 'fit_performed', 'cohort_statistics_computed',
             'formal_comparison_passed', 'formal_noninferiority_passed',
             'future_independent_oos', 'point_in_time_verified', 'promotion_allowed',
             'source_bytes_authenticated', 'winner_selected')
GAPS = ['CONTROL_REAL_TICKER_AND_ORIGINAL_TARGET_DISPLAY_REQUIRES_CONTROL_INPUTS',
        'FULL_DAILY_SID_HOLDINGS_AND_RISK_REQUIRES_EXECUTION_RAW_CLOSURE',
        'CONTINUOUS_SID_AND_CHAIN_EXPOSURE_NOT_SAVED_REQUIRES_SEPARATE_DERIVATION',
        'FULL_CHAIN_AGGREGATES_NOT_COMPUTED', 'WORKBOOK_CELL_READBACK_AND_VISUAL_ACCEPTANCE']
FORMAL = ['INDEPENDENT_COHORT_P50_P10_P90', 'FORMAL_COMPONENTWISE_NONINFERIORITY', 'FRESH_FORWARD_OOS_AND_PIT']
TABLES = (
    ('轨道与阻断', ['轨道序号', '汇率模式', '目标lane', '账户轨', '候选状态', '控制状态', '原阻断JSON', '候选原因', '控制原因']),
    ('已存路径指标', ['轨道序号', '汇率模式', '目标lane', '账户轨', '角色', '状态', '累计收益精确分数', '年化收益原Decimal文本', '最大回撤精确分数']),
    ('到NAV的逐项距离', ['轨道序号', '汇率模式', '目标lane', '账户轨', '候选年化绝对距离', '候选回撤绝对距离', '控制年化绝对距离', '控制回撤绝对距离', '年化距离候选减控制', '回撤距离候选减控制', '原距离JSON']),
    ('两种NAV参考', ['汇率模式', '状态', '原缺失日期JSON', '累计收益精确分数', '年化收益原Decimal文本', '最大回撤精确分数']),
    ('48个决策位置', ['原序号', '日期', '汇率模式', '目标lane', '原状态', '完整原证据JSON']),
    ('已存归一轨迹', ['轨道序号', '汇率模式', '目标lane', '账户轨', '角色', '日期', '归一净值精确分数']),
    ('来源索引', ['角色', '路径', 'SHA256']),
    ('范围与未晋级', ['项目', '原文']),
    ('候选原目标证券', ['原坐标', '决策日期', '汇率模式', '目标lane', '状态', 'SID', '真实ticker', 'issuer', '原目标权重文本', '执行日期', '原风险链标签', '来源JSON']),
    ('已保存决策风险', ['轨道序号', '汇率模式', '目标lane', '账户轨', '角色', '决策日期', '状态', '原风险JSON', '完整原决策JSON', '来源JSON']),
    ('决策逐SID原暴露', ['轨道序号', '汇率模式', '目标lane', '账户轨', '角色', '决策日期', 'SID', '原实际权重文本', '原风险链标签', '标签观察日期', '来源JSON']),
)


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))


def same(actual, expected, label):
    check(json_text(actual) == json_text(expected), 'Presentation differs: ' + label)


def fraction_string(source):
    check(set(source) == {'numerator', 'denominator'}, 'Ratio fields')
    numerator, denominator = source['numerator'], source['denominator']
    check(type(numerator) is str and re.fullmatch('-?(0|[1-9][0-9]*)', numerator), 'Ratio numerator')
    check(type(denominator) is str and re.fullmatch('[1-9][0-9]*', denominator), 'Ratio denominator')
    return numerator + '/' + denominator


def metric_strings(source, calendar):
    if source is None:
        return [None, None, None]
    same(source['observation_count'], 120, 'metric count')
    same([point['session'] for point in source['wealth']], calendar, 'metric date coverage')
    check(type(source['annualized_return_diagnostic_decimal']) is str, 'Original annualized decimal')
    return [fraction_string(source['cumulative_return']), source['annualized_return_diagnostic_decimal'], fraction_string(source['maximum_drawdown'])]


def inspect_presentation(*, presentation, comparison_document, publication, audit, candidate_inputs_document, references):
    check(set(references) == {'comparison', 'publication', 'audit', 'reader', 'candidate_inputs'}, 'Five reference roles')
    for value in references.values():
        check(set(value) == {'path', 'sha256'} and type(value['path']) is str and bool(value['path']), 'Source reference')
        check(type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']), 'Source SHA')
    check(comparison_document['schema'] == 'MULTIDECISION_PATH_COMPARISON_DOCUMENT_V1', 'K document')
    check(publication['schema'] == 'MULTIDECISION_PATH_COMPARISON_PUBLICATION_V1', 'K publication')
    check(audit['schema'] == 'MULTIDECISION_PATH_COMPARISON_INDEPENDENT_READBACK_V1' and audit['status'] == 'PASS', 'Original independent PASS')
    same(audit['scope'], 'SAVED16_FULL_PATH_METRICS_AND_PAIRED_DISTANCES_NOT_ACCOUNT_REAUDIT_OR_COHORT_GATE', 'Audit scope')
    same(audit['reader_sha256'], references['reader']['sha256'], 'Reader source')
    same(publication['comparison_reference'], references['comparison'], 'Published comparison')
    same(audit['comparison_reference'], references['comparison'], 'Audited comparison')
    same(audit['publication_reference'], references['publication'], 'Audited publication')
    for parent in (publication, audit):
        same(parent['input_references'], comparison_document['input_references'], 'Parent input closure')
    same(publication['source_hashes'], comparison_document['source_hashes'], 'K producer source union')
    same(references['candidate_inputs'], comparison_document['input_references']['candidate_inputs'], 'Input reference')
    check(candidate_inputs_document['schema'] == 'MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1', 'Candidate input schema')
    original = comparison_document['comparison']
    check(original['schema'] == 'MULTIDECISION_SAME_WINDOW_PATH_DIAGNOSTIC_V1', 'Saved comparison schema')
    inputs = candidate_inputs_document['inputs']
    coordinates = inputs['outer_coordinate_rows_preserved']
    calendar = original['calendar']
    check(len(calendar) == 120 and len(set(calendar)) == 120 and calendar == sorted(calendar), 'Full calendar')
    same(original['missing_formal_evidence'], FORMAL, 'Formal evidence missing')
    for body in (original, inputs, audit['inspection']):
        for key, count in (('coordinate_count', 48), ('lane_count', 8), ('track_count', 16)):
            same(body[key], count, 'Source domain ' + key)
    for body in (comparison_document, publication, audit):
        for key in ('formal_comparison_passed', 'formal_noninferiority_passed', 'future_independent_oos', 'point_in_time_verified', 'promotion_allowed', 'fit_performed', 'cohort_statistics_computed'):
            check(body[key] is False, 'Source diagnostic authority')
    check(len(coordinates) == 48 and len(inputs['rows']) == 8 and len(original['rows']) == 16, 'All source positions')
    dates = [coordinates[index]['coordinate'][0] for index in range(0, 48, 8)]
    check(len(set(dates)) == 6 and dates == sorted(dates), 'Decision date ordering')
    for index, coordinate in enumerate(coordinates):
        same(coordinate['coordinate_index'], index, 'Decision index')
        same(coordinate['coordinate'], [dates[index // 8], FX[(index % 8) // 4], OBJECTIVES[index % 4]], 'Decision coordinate')
    nav = original['nav_modes_preserved']
    check(set(nav['modes']) == set(FX), 'Both NAV modes')
    for key in ('promotion_allowed', 'point_in_time_verified', 'formal_comparison_passed', 'future_independent_oos', 'cohort_statistics_computed'):
        check(nav[key] is False, 'NAV authority')

    fixed = dict(schema='MULTIDECISION_PATH_CHINESE_PRESENTATION_V1', scope='PURE_SAVED_EVIDENCE_PROJECTION_NOT_SOURCE_AUTHENTICATION', coordinate_count=48, lane_count=8, track_count=16,
                 original_comparison_preserved=original, original_coordinates_preserved=coordinates, references=references,
                 remaining_delivery_gaps=GAPS, full_h_delivery_complete=False, financial_recomputation_performed=False, actual_publication_performed=False,
                 **dict.fromkeys(AUTHORITY, False))
    same({key: value for key, value in presentation.items() if key != 'tables'}, fixed, 'Entire envelope and original evidence')
    check(type(presentation['tables']) is list and len(presentation['tables']) == 11, 'Eleven ordered tables')
    positions = [0] * 11
    cells = 0
    for actual, (name, headers) in zip(presentation['tables'], TABLES):
        same({key: value for key, value in actual.items() if key != 'rows'}, dict(name=name, headers=headers, all_cells_literal=True, financial_numeric_conversion_performed=False), 'Table header and authority')
        check(type(actual['rows']) is list, 'Table rows')

    def accept(table_index, expected):
        nonlocal cells
        offset = positions[table_index]
        rows = presentation['tables'][table_index]['rows']
        check(offset < len(rows), 'Missing projected row')
        same(rows[offset], expected, TABLES[table_index][0] + '/' + str(offset))
        positions[table_index] += 1
        cells += len(expected)

    for index, row in enumerate(original['rows']):
        mode_index, objective_index, track_index = index // 8, (index // 2) % 4, index % 2
        same(row['coordinate'], [FX[mode_index], OBJECTIVES[objective_index], ('CONTINUOUS', 'WHOLE_LOT')[track_index]], 'Track identity')
        same(row['track_index'], index, 'Track ordinal')
        same(row['nav_mode'], FX[mode_index], 'Track NAV identity')
        for body in (original, row):
            for key in AUTHORITY:
                check(body[key] is False, 'Comparison authority')
        prepared = inputs['rows'][index // 2]
        same([prepared['fx_mode'], prepared['lane']], row['coordinate'][:2], 'Prepared lane identity')
        same(prepared['coordinate_indexes'], list(range(index // 2, 48, 8)), 'Lane decision coverage')
        same(row['prepared_blocking_reasons']['candidate'], prepared['tracks'][track_index]['blocking_reasons'], 'Original blocker')
        prefix = [index, FX_LABEL[mode_index], OBJECTIVE_LABEL[objective_index], ACCOUNT_LABEL[track_index]]
        accept(0, prefix + [row['candidate']['status'], row['control']['status'], json_text(row['prepared_blocking_reasons']), row['candidate']['reason'], row['control']['reason']])
        for role, role_label in (('candidate', '候选'), ('control', '原八只控制')):
            path = row[role]
            metric = path['metrics']
            check(path['status'] in ('SAVED_PATH_DIAGNOSTIC', 'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT'), 'Path status')
            check((metric is None) == (path['status'] == 'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT'), 'Metric absence')
            accept(1, prefix + [role_label, path['status']] + metric_strings(metric, calendar))
            if metric is not None:
                for point in metric['wealth']:
                    accept(5, prefix + [role_label, point['session'], fraction_string(point['normalized_wealth'])])
            record_kind = 'rebalances' if track_index == 0 else 'decisions'
            records = path.get('saved_execution_diagnostics', {}).get(record_kind, [])
            check(len({record['decision_date'] for record in records}) == len(records), 'Unique saved decision records')
            check(all(record['decision_date'] in dates for record in records), 'Saved decision domain')
            for date in dates:
                risk_prefix = prefix + [role_label, date]
                matches = [(number, record) for number, record in enumerate(records) if record['decision_date'] == date]
                pointer = dict(references['comparison'], json_pointer='/comparison/rows/' + str(index) + '/' + role)
                if not matches:
                    accept(9, risk_prefix + ['原决策记录未提供', None, None, json_text(pointer)])
                    continue
                number, record = matches[0]
                pointer['json_pointer'] += '/saved_execution_diagnostics/' + record_kind + '/' + str(number)
                risk = record.get('decision_risk')
                if risk is None:
                    accept(9, risk_prefix + ['原决策未保存风险数值', None, json_text(record), json_text(pointer)])
                else:
                    accept(9, risk_prefix + ['已保存决策风险', json_text(risk), json_text(record), json_text(pointer)])
                    for sid in risk['actual_weights']:
                        accept(10, risk_prefix + [sid, json_text(risk['actual_weights'][sid]), record.get('risk_chains', {}).get(sid), record.get('risk_chain_observation_dates', {}).get(sid), json_text(pointer)])
        distance = row['distances']
        values = []
        for owner, fields in (('candidate', ('annualized_return_absolute_distance', 'maximum_drawdown_absolute_distance')), ('control', ('annualized_return_absolute_distance', 'maximum_drawdown_absolute_distance')), ('candidate_minus_control_absolute_distance', ('annualized_return', 'maximum_drawdown'))):
            values += [None, None] if distance[owner] is None else [distance[owner][field] for field in fields]
        check(all(value is None or type(value) is str for value in values), 'Original distance string')
        accept(2, prefix + values + [json_text(distance)])

    for mode_index, mode in enumerate(FX):
        entry = nav['modes'][mode]
        same(entry['mode'], mode, 'NAV mode')
        accept(3, [FX_LABEL[mode_index], entry['status'], json_text(entry['missing_sessions'])] + metric_strings(entry['metrics'], calendar))
        if entry['metrics'] is not None:
            for point in entry['metrics']['wealth']:
                accept(5, [None, FX_LABEL[mode_index], None, None, '012922参考', point['session'], fraction_string(point['normalized_wealth'])])
    for index, coordinate in enumerate(coordinates):
        accept(4, [index, coordinate['coordinate'][0], FX_LABEL[(index % 8) // 4], OBJECTIVE_LABEL[index % 4], coordinate['status'], json_text(coordinate)])
    # Publisher's fixed BOUND role order, independent of decoded JSON key order.
    for role in ('comparison', 'publication', 'audit', 'reader', 'candidate_inputs'):
        reference = references[role]
        accept(6, [role, reference['path'], reference['sha256']])
    for row in [['范围', original['scope']], ['缺失正式证据', json_text(FORMAL)], ['NAV原限制', json_text(nav['original_alignment_limitations'])], ['FX原语义', json_text(nav['original_fx_context'])], ['数值口径', '已存binary64路径的精确分数与原Decimal80年化诊断；不是精确经济值或正式cohort统计'], ['本阶段尚缺', json_text(GAPS)]]:
        accept(7, row)
    for lane_index, lane in enumerate(inputs['rows']):
        schedule = lane['original_targets_schedule']
        check(len({entry['decision_date'] for entry in schedule}) == len(schedule), 'Unique target dates')
        check(all(entry['decision_date'] in dates for entry in schedule), 'Target date domain')
        for date_index, date in enumerate(dates):
            prefix = [date_index * 8 + lane_index, date, FX_LABEL[lane_index // 4], OBJECTIVE_LABEL[lane_index % 4]]
            pointer = dict(references['candidate_inputs'], json_pointer='/inputs/rows/' + str(lane_index) + '/original_targets_schedule')
            matches = [entry for entry in schedule if entry['decision_date'] == date]
            if not matches:
                accept(8, prefix + ['原目标未提供', None, None, None, None, None, None, json_text(pointer)])
                continue
            entry = matches[0]
            check(bool(entry['targets']), 'Original targets nonempty')
            labels = lane['tracks'][0]['stateful_input']['risk_chains_by_decision'].get(date, {})
            same(labels, lane['tracks'][1]['stateful_input']['risk_chains_by_decision'].get(date, {}), 'Target labels identical between tracks')
            for sid, target in entry['targets'].items():
                accept(8, prefix + ['已保存原目标', sid, target['ticker'], target['issuer_id'], json_text(target['target_weight']), entry['execution_date'], labels.get(sid), json_text(pointer)])
    for index, actual in enumerate(presentation['tables']):
        check(len(actual['rows']) == positions[index], 'Extra or unverified row: ' + actual['name'])
    check(positions[9] == 192, 'All role-track-decision risk positions')
    return dict(schema='MULTIDECISION_PATH_PRESENTATION_INSPECTION_V1', status='PASS', scope='ALL11_TABLES_EXACT_SAVED_FIELD_PROJECTION_NOT_FINANCIAL_RECOMPUTATION',
                coordinate_count=48, lane_count=8, track_count=16, table_count=11, checked_cell_count=cells,
                table_row_counts=[dict(name=name, count=positions[index]) for index, (name, _) in enumerate(TABLES)],
                producer_called=False, producer_helpers_called=False, financial_recomputation_performed=False,
                source_bytes_authenticated=False, full_h_delivery_complete=False, promotion_allowed=False)
