"""Pure saved holdings/risk projection. No IO, arithmetic, account or risk calls.

References are structural declarations until separately authenticated by a source
wrapper. Internal engine column labels never substitute for saved real tickers.
"""
from copy import deepcopy
import json
import re

MODES = ('STRICT_SAME_SESSION_FX', 'BACKWARD_LATEST_VALID_FX')
LANES = ('RETURN', 'BAD_TAIL', 'DRAWDOWN', 'TARGET_ENVELOPE')
TRACKS = ('CONTINUOUS', 'WHOLE_LOT')
FALSE = ('source_bytes_authenticated', 'account_executed', 'risk_recomputed',
         'chain_aggregates_computed', 'financial_recomputation_performed',
         'point_in_time_verified', 'promotion_allowed', 'full_h_delivery_complete')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def exact(left, right):
    require(text(left) == text(right), 'Exact original evidence')


def reference(value):
    require(type(value) is dict and set(value) == {'path', 'sha256'}, 'File reference')
    require(type(value['path']) is str and bool(value['path']), 'Reference path')
    require(type(value['sha256']) is str and re.fullmatch('[a-f0-9]{64}', value['sha256']), 'Reference SHA')


def pointer(value, location):
    return dict(value, json_pointer=location)


def table(name, headers, rows):
    return dict(name=name, headers=headers, rows=rows, all_cells_literal=True,
                financial_numeric_conversion_performed=False)


def identity_map(rows, control=False):
    result = {}
    for entry in rows:
        item = entry if control else entry['coordinate_preserved']
        sid = item['security_id']
        require(type(sid) is str and sid and sid not in result, 'Unique saved SID identity')
        ticker = item['ticker']
        require(type(ticker) is str and ticker and not ticker.startswith(('SID_COLUMN_', 'CONTROL_SID_COLUMN_')), 'Real saved ticker required')
        require(type(item['issuer_id']) is str and item['issuer_id'], 'Original issuer')
        result[sid] = item
    return result


def build_supplement(*, candidate_inputs, control_inputs, candidate_execution,
                     control_execution, raw_documents, references):
    """Project 32 original slots and every saved daily row. No risk derivation.

    raw_documents maps candidate/control to 16 ordered None-or-{reference,document}
    entries; None is required for blocked slots. Four references bind the input
    and execution documents. A wrapper must separately bind their original audits.
    """
    roles = ('candidate', 'control')
    require(set(references) == {'candidate_inputs', 'control_inputs', 'candidate_execution', 'control_execution'}, 'Four fixed document roles')
    for ref in references.values(): reference(ref)
    require(set(raw_documents) == set(roles), 'Two raw role lists')
    inputs = {'candidate': candidate_inputs, 'control': control_inputs}
    results = {'candidate': candidate_execution, 'control': control_execution}
    schemas = {'candidate': ('MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1', 'MULTIDECISION_ACCOUNT_EXECUTION_RESULT_V1', 'MULTIDECISION_ACCOUNT_RAW_RETURN_V1'),
               'control': ('MULTIDECISION_ORIGINAL_EIGHT_INPUTS_DOCUMENT_V1', 'MULTIDECISION_INCUMBENT_ACCOUNT_EXECUTION_RESULT_V1', 'MULTIDECISION_INCUMBENT_ACCOUNT_RAW_RETURN_V1')}
    definition = control_inputs['inputs']['original_control_preserved']['complete_original_definition']['securities']
    control_ids = identity_map(definition, True)
    require(len(control_ids) == 8, 'Original eight identities')
    identities, targets, daily_rows, holdings_rows, risk_rows, blocked = [], [], [], [], [], []
    saved_raw = {'candidate': [], 'control': []}
    global_calendar = None
    counts = dict(returned_paths=0, blocked_paths=0, daily_rows=0, saved_risk_rows=0, missing_risk_rows=0)
    for role in roles:
        inp, execution = inputs[role], results[role]
        require(inp['schema'] == schemas[role][0] and execution['schema'] == schemas[role][1], 'Role-specific schemas')
        require(execution['status'] == 'ALL16_INPUT_SLOTS_PROCESSED_PENDING_INDEPENDENT_READBACK' and execution['failure'] is None, 'Complete successful execution result')
        exact(execution['input_references']['inputs'], references[role + '_inputs'])
        body = inp['inputs']
        for key, value in (('coordinate_count', 48), ('lane_count', 8), ('track_count', 16)):
            require(type(body[key]) is int and body[key] == value, 'Complete input domain')
        require(len(body['rows']) == 8 and len(execution['rows']) == len(raw_documents[role]) == 16, 'All input/execution/raw slots')
        for doc in (inp, execution):
            require(doc['point_in_time_verified'] is False and doc['promotion_allowed'] is False, 'Original conditional limits')
        for lane_index, lane in enumerate(body['rows']):
            mode, objective = MODES[lane_index // 4], LANES[lane_index % 4]
            exact([lane['fx_mode'], lane['lane']], [mode, objective])
            exact(lane['coordinate_indexes'], list(range(lane_index, 48, 8)))
            require(len(lane['tracks']) == 2, 'Both tracks')
            ids = control_ids if role == 'control' else identity_map(lane['source_slots'])
            if role == 'candidate':
                for entry in lane['original_targets_schedule']:
                    for sid, target in entry['targets'].items():
                        require(sid in ids, 'Original target has saved SID identity')
                        exact([target['ticker'], target['issuer_id']], [ids[sid]['ticker'], ids[sid]['issuer_id']])
            identity_location = '/inputs/original_control_preserved/complete_original_definition/securities' if role == 'control' else f'/inputs/rows/{lane_index}/source_slots'
            identity_ref = pointer(references[role + '_inputs'], identity_location)
            for sid, item in ids.items():
                identities.append([role, mode, objective, sid, item['ticker'], item['issuer_id'], text(item), text(identity_ref)])
            if role == 'control':
                schedule = lane['tracks'][0]['engine_binding']['keyword_arguments']['schedule']
                exact(schedule, lane['tracks'][1]['engine_binding']['keyword_arguments']['schedule'])
                require(len(schedule) == 6 and len({e['decision_date'] for e in schedule}) == 6, 'Six original control targets')
                for schedule_index, entry in enumerate(schedule):
                    require(set(entry['targets']) == set(ids), 'Eight original target slots')
                    for sid, target in entry['targets'].items():
                        exact(target['target_weight'], ids[sid]['target_weight'])
                        exact(target['issuer_id'], ids[sid]['issuer_id'])
                        schedule_ref = pointer(references['control_inputs'], f'/inputs/rows/{lane_index}/tracks/0/engine_binding/keyword_arguments/schedule/{schedule_index}')
                        targets.append([mode, objective, entry['decision_date'], entry['execution_date'], sid, ids[sid]['ticker'], ids[sid]['issuer_id'], text(target['target_weight']), target['ticker'], text(identity_ref), text(schedule_ref)])
            for offset, track in enumerate(lane['tracks']):
                index = lane_index * 2 + offset
                kind = TRACKS[offset]
                require(track['track'] == kind, 'Original track order')
                row = execution['rows'][index]
                exact([row['track_index'], row['fx_mode'], row['lane'], row['track']], [index, mode, objective, kind])
                prefix = [role, index, mode, objective, kind]
                bundle = raw_documents[role][index]
                if row['outcome'] == 'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT':
                    require(role == 'candidate' and bundle is None and row['raw_reference'] is None and row['call_invoked'] is False, 'Blocked is not an empty executed account')
                    exact(row['blocking_reasons'], track['blocking_reasons'])
                    blocked.append(prefix + [text(row['blocking_reasons']), text(pointer(references[role + '_execution'], f'/rows/{index}'))])
                    saved_raw[role].append(None);counts['blocked_paths'] += 1
                    continue
                require(row['outcome'] == 'ACCOUNT_RETURNED_PENDING_INDEPENDENT_READBACK' and row['call_invoked'] is True, 'Returned account role')
                require(type(bundle) is dict and set(bundle) == {'reference', 'document'}, 'Explicit raw bundle')
                reference(bundle['reference']);exact(bundle['reference'], row['raw_reference'])
                raw = bundle['document']
                require(raw['schema'] == schemas[role][2] and raw['returned'] is True and raw['call_invoked'] is True and raw['error'] is None, 'Successful saved RAW')
                exact(raw['input_references'], execution['input_references'])
                exact(raw['started_reference'], row['started_reference'])
                require(raw['point_in_time_verified'] is False and raw['promotion_allowed'] is False, 'RAW conditional limits')
                saved_raw[role].append(deepcopy(bundle));counts['returned_paths'] += 1
                days = raw['result']['daily']
                calendar = [day['session'] for day in days]
                require(len(calendar) == 120 and calendar == sorted(set(calendar)), 'Complete saved 120-day calendar')
                kwargs = track['engine_binding']['keyword_arguments']
                exact(calendar, kwargs['closes']['index'])
                if global_calendar is None: global_calendar = calendar
                exact(calendar, global_calendar)
                aliases = {sid: target['ticker'] for entry in kwargs['schedule'] for sid, target in entry['targets'].items()}
                for n, day in enumerate(days):
                    at = pointer(bundle['reference'], f'/result/daily/{n}')
                    day_prefix = prefix + [day['session']]
                    daily_rows.append(day_prefix + [text(day), text(at)]);counts['daily_rows'] += 1
                    quantities = day['holdings'] if kind == 'CONTINUOUS' else day['shares']
                    for sid, value in quantities.items():
                        require(sid in ids and sid in aliases, 'Every holding has saved identity and engine alias')
                        internal = value['ticker'] if kind == 'CONTINUOUS' else day['tickers'][sid]
                        exact(internal, aliases[sid])
                        if kind == 'CONTINUOUS': exact(value['issuer_id'], ids[sid]['issuer_id'])
                        quantity = value['shares'] if kind == 'CONTINUOUS' else value
                        holdings_rows.append(day_prefix + [sid, ids[sid]['ticker'], ids[sid]['issuer_id'], internal, text(quantity), text(identity_ref), text(at)])
                    if not quantities:
                        holdings_rows.append(day_prefix + [None, None, None, None, None, text(identity_ref), text(at)])
                    risk = day.get('risk')
                    if risk is None:
                        require(role == 'candidate' and kind == 'CONTINUOUS', 'Only original missing candidate continuous risk')
                        counts['missing_risk_rows'] += 1
                        status = 'ORIGINAL_RISK_NOT_SAVED_NO_DERIVATION'
                    else:
                        require(type(risk) is dict, 'Original risk mapping')
                        counts['saved_risk_rows'] += 1;status = 'SAVED_RISK_UNCHANGED'
                    risk_rows.append(day_prefix + [status, None if risk is None else text(risk), text(day.get('risk_chains')), text(day.get('risk_chain_observation_dates')), text(at)])
    exact(counts, dict(returned_paths=24, blocked_paths=8, daily_rows=2880, saved_risk_rows=2400, missing_risk_rows=480))
    tables = [table('原身份与内部列分离', ['角色','FX','lane','SID','真实ticker','issuer','完整原身份JSON','身份来源'], identities),
              table('控制原目标', ['FX','lane','决策日期','执行日期','SID','真实ticker','issuer','原权重文本','内部列名','身份来源','原目标来源'], targets),
              table('完整每日原记录', ['角色','轨道序号','FX','lane','账户轨','日期','原记录JSON','RAW来源'], daily_rows),
              table('每日SID原持仓', ['角色','轨道序号','FX','lane','账户轨','日期','SID','真实ticker','issuer','内部列名','原数量文本','身份来源','RAW来源'], holdings_rows),
              table('每日原风险与缺口', ['角色','轨道序号','FX','lane','账户轨','日期','状态','原风险JSON','原链标签JSON','原标签日期JSON','RAW来源'], risk_rows),
              table('未执行阻断轨道', ['角色','轨道序号','FX','lane','账户轨','原阻断JSON','原执行槽来源'], blocked)]
    return dict(schema='MULTIDECISION_SAVED_HOLDINGS_SUPPLEMENT_V1', scope='SAVED_RAW_PROJECTION_NOT_RISK_DERIVATION',
                counts=counts, calendar=global_calendar, tables=tables, references=deepcopy(references),
                original_raw_bundles_preserved=saved_raw, original_control_definition_preserved=deepcopy(definition),
                original_identity_scope='PRESERVE_SAVED_CONDITIONAL_IDENTITY_NOT_HISTORICAL_IDENTITY_VERIFICATION',
                remaining_gaps=['CANDIDATE_CONTINUOUS_DAILY_RISK_NOT_SAVED', 'NEW_CHAIN_AGGREGATES_NOT_COMPUTED', 'SOURCE_PUBLICATION_AND_INDEPENDENT_READBACK', 'WORKBOOK_CELL_READBACK_AND_VISUAL_ACCEPTANCE'],
                **dict.fromkeys(FALSE, False))
