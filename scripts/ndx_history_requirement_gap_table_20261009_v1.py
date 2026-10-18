"""Render saved historical requirements by SID/freeze date; no economic replay."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate source key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def project(document, source_reference):
    if document['schema'] != 'BULK_HISTORY_REQUIREMENTS_DOCUMENT_V1':
        raise ValueError('Expected saved requirements schema')
    requirements = document['requirements']
    if requirements['schema'] != 'BULK_CONDITIONAL_HISTORY_REQUIREMENTS_V1':
        raise ValueError('Expected saved conditional requirements')
    rows = []
    identities = set()
    for scenario_index, scenario in enumerate(requirements['scenarios']):
        windows = {window['window_index']: window for window in scenario['windows']}
        if len(windows) != len(scenario['windows']):
            raise ValueError('Duplicate source window')
        for security_index, security in enumerate(scenario['security_rows']):
            coordinate = security['coordinate']
            if len(security['requirements']) != len(windows):
                raise ValueError('Every security retains all source windows')
            for requirement_index, requirement in enumerate(security['requirements']):
                window_index = requirement['window_index']
                window = windows[window_index]
                identity = (scenario_index, coordinate['security_id'], window_index)
                if identity in identities:
                    raise ValueError('Duplicate security/window identity')
                identities.add(identity)
                pointer = f'/requirements/scenarios/{scenario_index}/security_rows/{security_index}/requirements/{requirement_index}'
                window_position = scenario['windows'].index(window)
                rows.append(dict(coordinate=deepcopy(coordinate), scenario_index=scenario_index,
                    price_window_length=scenario['price_window_length'], window_index=window_index,
                    training_freeze_close_date=window['training_freeze_close_date'],
                    required_price_dates=deepcopy(window['required_price_dates']),
                    evaluation_price_dates=deepcopy(window['evaluation_price_dates']),
                    original_requirement=deepcopy(requirement),
                    requirement_reference=dict(**source_reference, json_pointer=pointer),
                    coordinate_reference=dict(**source_reference,
                        json_pointer=f'/requirements/scenarios/{scenario_index}/security_rows/{security_index}/coordinate'),
                    window_reference=dict(**source_reference,
                        json_pointer=f'/requirements/scenarios/{scenario_index}/windows/{window_position}')))
    reasons = Counter(key for row in rows for key, value in row['original_requirement'].items()
        if key.endswith('_verified') and value is False)
    return dict(schema='HISTORICAL_REQUIREMENT_SID_FREEZE_GAP_PROJECTION_V1',
        source_reference=source_reference, rows=rows,
        summary=dict(row_count=len(rows), security_count=len({row['coordinate']['security_id'] for row in rows}),
            scenario_count=len(requirements['scenarios']),
            price_window_lengths=[scenario['price_window_length'] for scenario in requirements['scenarios']],
            source_status_counts=dict(Counter(row['original_requirement']['status'] for row in rows)),
            unverified_flag_counts=dict(sorted(reasons.items())),
            rows_with_missing_price_dates=sum(bool(row['original_requirement']['missing_price_dates']) for row in rows),
            rows_with_missing_saved_fields=sum(bool(row['original_requirement']['saved_missing_field_rows']) for row in rows)),
        benchmark_gaps=deepcopy(requirements['benchmark_gaps']),
        observed_provenance_reference=dict(**source_reference, json_pointer='/requirements/observed_provenance_and_missing'),
        observed_provenance_denominator=requirements['observed_provenance_denominator'],
        conditional_security_denominator=requirements['security_denominator'],
        conditional_issuer_denominator=requirements['issuer_denominator'],
        scope='Exact saved requirement/window/coordinate projection, not raw market or transitive source verification',
        economic_recomputation_performed=False, full_ndx_certified=False, point_in_time_verified=False,
        source_authenticity_verified=False, legal_training_input_admitted=False,
        future_independent_oos=False, promotion_allowed=False, live_mutation_allowed=False)


def markdown(projected):
    summary = projected['summary']
    lines = ['# 历史证据缺口：逐证券／训练冻结日', '',
        '本表只展开已保存的历史要求，不重新计算收益、价格或风险，不解除任何准入阻断。', '',
        f"共有 {summary['security_count']} 个条件证券、{summary['scenario_count']} 类窗口、{summary['row_count']} 个证券／窗口要求。观察成员分母为 {projected['observed_provenance_denominator']}；条件池为 {projected['conditional_security_denominator']} 证券／{projected['conditional_issuer_denominator']} 发行人，不能当完整点时 Nasdaq100。", '',
        f"缺收盘日期的行数：{summary['rows_with_missing_price_dates']}；缺已保存字段的行数：{summary['rows_with_missing_saved_fields']}。数值元数据齐全不代表身份、成员资格、公司行动、量单位和可得时点已证实。", '',
        '机器表保留每行原要求全文、全部精确日期和来源 JSON pointer；下面只汇总同一证券在全部窗口的缺口。', '',
        '|ticker|证券ID|冻结日范围|窗口数|身份假设未覆盖日期数（各窗口相加）|缺价格日期数|',
        '|---|---|---|---:|---:|---:|']
    grouped = {}
    for row in projected['rows']:
        grouped.setdefault(row['coordinate']['security_id'], []).append(row)
    for security_id, rows in sorted(grouped.items(), key=lambda item: item[1][0]['coordinate']['ticker']):
        dates = sorted(row['training_freeze_close_date'] for row in rows)
        uncovered = sum(len(row['original_requirement']['identity_assumption_uncovered_price_dates']) for row in rows)
        missing = sum(len(row['original_requirement']['missing_price_dates']) for row in rows)
        lines.append(f"|{rows[0]['coordinate']['ticker']}|{security_id}|{dates[0]} 至 {dates[-1]}|{len(rows)}|{uncovered}|{missing}|")
    lines += ['', '## 尚未证实的原门', '', '|原字段|行数|', '|---|---:|']
    lines += [f'|{name}|{count}|' for name, count in summary['unverified_flag_counts'].items()]
    lines += ['', '身份区间、provider映射、历史风险区间、公司行动与股息现金流、量单位和可得时点需按机器表对应SID及冻结日补原件。原表没有提供独立63日流动性日期清单，本表不从自然日猜造；应沿原训练／流动性契约另取日期。', '',
        'benchmark缺口保持原值：' + '、'.join(projected['benchmark_gaps']) + '。', '',
        '历史要求覆盖不等于全k组成／权重最优、正式双基准准入、未来一年独立OOS或实盘建议。', '']
    return '\n'.join(lines)


def run(source_path, source_sha256, output_directory):
    source = Path(source_path).resolve(strict=True)
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 64 * 1024**2:
        raise ValueError('Bounded regular saved requirements')
    raw = source.read_bytes()
    if digest(raw) != source_sha256:
        raise ValueError('Saved source hash mismatch')
    reference = dict(path=str(source), sha256=source_sha256)
    document = decode(raw)
    result = project(document, reference)
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'gap_table.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    with (output / 'REPORT.md').open('x', encoding='utf-8') as stream:
        stream.write(markdown(result))
    if digest(source.read_bytes()) != source_sha256:
        raise ValueError('Source changed during projection')
    return result['summary']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-path', required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--output-directory', required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source_path, args.source_sha256, args.output_directory), ensure_ascii=False))
