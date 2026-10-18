"""Independent six-table saved-field checker. No producer, account or IO calls."""
import json

MODES = ('STRICT_SAME_SESSION_FX', 'BACKWARD_LATEST_VALID_FX')
LANES = ('RETURN', 'BAD_TAIL', 'DRAWDOWN', 'TARGET_ENVELOPE')
TRACKS = ('CONTINUOUS', 'WHOLE_LOT')
HEADERS = (
    ('原身份与内部列分离', ['角色','FX','lane','SID','真实ticker','issuer','完整原身份JSON','身份来源']),
    ('控制原目标', ['FX','lane','决策日期','执行日期','SID','真实ticker','issuer','原权重文本','内部列名','身份来源','原目标来源']),
    ('完整每日原记录', ['角色','轨道序号','FX','lane','账户轨','日期','原记录JSON','RAW来源']),
    ('每日SID原持仓', ['角色','轨道序号','FX','lane','账户轨','日期','SID','真实ticker','issuer','内部列名','原数量文本','身份来源','RAW来源']),
    ('每日原风险与缺口', ['角色','轨道序号','FX','lane','账户轨','日期','状态','原风险JSON','原链标签JSON','原标签日期JSON','RAW来源']),
    ('未执行阻断轨道', ['角色','轨道序号','FX','lane','账户轨','原阻断JSON','原执行槽来源']),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def equal(actual, wanted, message):
    require(packed(actual) == packed(wanted), message)


def location(reference, path):
    return packed(dict(reference, json_pointer=path))


def inspect_supplement(*, supplement, candidate_inputs, control_inputs, candidate_execution,
                       control_execution, raw_documents, references):
    require(set(references) == {'candidate_inputs','control_inputs','candidate_execution','control_execution'}, 'Four original references')
    require(set(raw_documents) == {'candidate','control'}, 'Both original raw lists')
    definition = control_inputs['inputs']['original_control_preserved']['complete_original_definition']['securities']
    require(len(definition) == 8, 'Original eight control identities')
    require(len(supplement['tables']) == 6, 'Six complete tables')
    progress = [0] * 6
    checked_cells = 0
    for table, (name, headers) in zip(supplement['tables'], HEADERS):
        equal({key: value for key, value in table.items() if key != 'rows'}, dict(name=name, headers=headers, all_cells_literal=True, financial_numeric_conversion_performed=False), 'Table metadata')

    def cell_row(number, row):
        nonlocal checked_cells
        actual = supplement['tables'][number]['rows']
        require(progress[number] < len(actual), 'Missing row')
        equal(actual[progress[number]], row, 'Original fields differ: ' + HEADERS[number][0] + '/' + str(progress[number]))
        progress[number] += 1
        checked_cells += len(row)

    calendar = None
    counts = dict(returned_paths=0, blocked_paths=0, daily_rows=0, saved_risk_rows=0, missing_risk_rows=0)
    for role, input_doc, executed in (('candidate', candidate_inputs, candidate_execution), ('control', control_inputs, control_execution)):
        expected_schemas = ('MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1', 'MULTIDECISION_ACCOUNT_EXECUTION_RESULT_V1', 'MULTIDECISION_ACCOUNT_RAW_RETURN_V1') if role == 'candidate' else ('MULTIDECISION_ORIGINAL_EIGHT_INPUTS_DOCUMENT_V1', 'MULTIDECISION_INCUMBENT_ACCOUNT_EXECUTION_RESULT_V1', 'MULTIDECISION_INCUMBENT_ACCOUNT_RAW_RETURN_V1')
        require(input_doc['schema'] == expected_schemas[0] and executed['schema'] == expected_schemas[1], 'Role-specific input/result schemas')
        require(len(raw_documents[role]) == len(executed['rows']) == 16, 'All sixteen raw slots')
        require(executed['failure'] is None and executed['status'] == 'ALL16_INPUT_SLOTS_PROCESSED_PENDING_INDEPENDENT_READBACK', 'Completed original request')
        equal(executed['input_references']['inputs'], references[role+'_inputs'], 'Original input binding')
        for doc in (input_doc, executed):
            require(doc['point_in_time_verified'] is False and doc['promotion_allowed'] is False, 'Source authority')
        body = input_doc['inputs']
        for key, n in (('coordinate_count',48),('lane_count',8),('track_count',16)):
            equal(body[key],n,'Complete source domain')
        require(len(body['rows']) == 8, 'Eight original lanes')
        for lane_number in range(8):
            lane = body['rows'][lane_number]
            mode, objective = MODES[lane_number//4], LANES[lane_number%4]
            equal([lane['fx_mode'], lane['lane']], [mode, objective], 'Lane coordinate')
            equal(lane['coordinate_indexes'], list(range(lane_number,48,8)), 'Six original decisions')
            require(len(lane['tracks']) == 2, 'Two account tracks')
            identity_records = definition if role == 'control' else [row['coordinate_preserved'] for row in lane['source_slots']]
            identities = {record['security_id']: record for record in identity_records}
            require(len(identities) == len(identity_records), 'Unique original identities')
            if role == 'candidate':
                for entry in lane['original_targets_schedule']:
                    for sid, target in entry['targets'].items():
                        require(sid in identities, 'Saved candidate target identity')
                        equal([target['ticker'], target['issuer_id']], [identities[sid]['ticker'], identities[sid]['issuer_id']], 'Candidate original target ticker and issuer')
            identity_path = '/inputs/original_control_preserved/complete_original_definition/securities' if role == 'control' else '/inputs/rows/'+str(lane_number)+'/source_slots'
            identity_pointer = location(references[role+'_inputs'], identity_path)
            for record in identity_records:
                cell_row(0,[role,mode,objective,record['security_id'],record['ticker'],record['issuer_id'],packed(record),identity_pointer])
            if role == 'control':
                schedules = [track['engine_binding']['keyword_arguments']['schedule'] for track in lane['tracks']]
                equal(schedules[0],schedules[1],'Two control schedules')
                require(len(schedules[0]) == 6,'Six control target positions')
                for n, entry in enumerate(schedules[0]):
                    require(set(entry['targets']) == set(identities),'All eight targets')
                    for sid,target in entry['targets'].items():
                        identity = identities[sid]
                        equal([target['target_weight'],target['issuer_id']], [identity['target_weight'],identity['issuer_id']], 'Original control target')
                        at = location(references['control_inputs'],f'/inputs/rows/{lane_number}/tracks/0/engine_binding/keyword_arguments/schedule/{n}')
                        cell_row(1,[mode,objective,entry['decision_date'],entry['execution_date'],sid,identity['ticker'],identity['issuer_id'],packed(target['target_weight']),target['ticker'],identity_pointer,at])
            for track_number, track in enumerate(lane['tracks']):
                index = lane_number*2+track_number
                kind = TRACKS[track_number]
                row = executed['rows'][index]
                equal([row['track_index'],row['fx_mode'],row['lane'],row['track']],[index,mode,objective,kind],'Original slot')
                require(track['track'] == kind,'Original input track')
                prefix = [role,index,mode,objective,kind]
                bundle = raw_documents[role][index]
                if row['outcome'] == 'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT':
                    require(role == 'candidate' and bundle is None and row['raw_reference'] is None and row['call_invoked'] is False,'Missing raw is blocked only')
                    equal(row['blocking_reasons'],track['blocking_reasons'],'Original blockers')
                    cell_row(5,prefix+[packed(row['blocking_reasons']),location(references[role+'_execution'],f'/rows/{index}')])
                    counts['blocked_paths'] += 1
                    continue
                require(row['outcome'] == 'ACCOUNT_RETURNED_PENDING_INDEPENDENT_READBACK' and row['call_invoked'] is True,'Original returned status')
                require(set(bundle) == {'reference','document'},'Original raw bundle')
                equal(bundle['reference'],row['raw_reference'],'Raw identity')
                raw = bundle['document']
                require(raw['schema'] == expected_schemas[2] and raw['point_in_time_verified'] is False and raw['promotion_allowed'] is False, 'Original raw schema and authority')
                require(raw['returned'] is True and raw['call_invoked'] is True and raw['error'] is None,'Original returned raw')
                equal(raw['input_references'],executed['input_references'],'Raw input references')
                equal(raw['started_reference'],row['started_reference'],'Raw start reference')
                counts['returned_paths'] += 1
                days = raw['result']['daily']
                kwargs = track['engine_binding']['keyword_arguments']
                dates = [day['session'] for day in days]
                require(len(dates) == 120 and dates == sorted(set(dates)),'Full original calendar')
                equal(dates,kwargs['closes']['index'],'Original price calendar')
                if calendar is None: calendar = dates
                equal(dates,calendar,'Same calendar across paths')
                aliases = {sid:target['ticker'] for entry in kwargs['schedule'] for sid,target in entry['targets'].items()}
                for day_index, day in enumerate(days):
                    pre = prefix+[day['session']]
                    at = location(bundle['reference'],f'/result/daily/{day_index}')
                    cell_row(2,pre+[packed(day),at])
                    counts['daily_rows'] += 1
                    positions = day['holdings'] if kind == 'CONTINUOUS' else day['shares']
                    for sid, value in positions.items():
                        identity = identities[sid]
                        internal = value['ticker'] if kind == 'CONTINUOUS' else day['tickers'][sid]
                        equal(internal,aliases[sid],'Original internal alias')
                        if kind == 'CONTINUOUS': equal(value['issuer_id'],identity['issuer_id'],'Holding issuer')
                        quantity = value['shares'] if kind == 'CONTINUOUS' else value
                        cell_row(3,pre+[sid,identity['ticker'],identity['issuer_id'],internal,packed(quantity),identity_pointer,at])
                    if not positions: cell_row(3,pre+[None,None,None,None,None,identity_pointer,at])
                    risk = day.get('risk')
                    if risk is None:
                        require(role == 'candidate' and kind == 'CONTINUOUS','Only saved missing risk scope')
                        counts['missing_risk_rows'] += 1
                    else: counts['saved_risk_rows'] += 1
                    cell_row(4,pre+['ORIGINAL_RISK_NOT_SAVED_NO_DERIVATION' if risk is None else 'SAVED_RISK_UNCHANGED',None if risk is None else packed(risk),packed(day.get('risk_chains')),packed(day.get('risk_chain_observation_dates')),at])
    equal(counts,dict(returned_paths=24,blocked_paths=8,daily_rows=2880,saved_risk_rows=2400,missing_risk_rows=480),'Full historical scope')
    expected = dict(schema='MULTIDECISION_SAVED_HOLDINGS_SUPPLEMENT_V1',scope='SAVED_RAW_PROJECTION_NOT_RISK_DERIVATION',counts=counts,calendar=calendar,references=references,
                    original_raw_bundles_preserved=raw_documents,original_control_definition_preserved=definition,
                    original_identity_scope='PRESERVE_SAVED_CONDITIONAL_IDENTITY_NOT_HISTORICAL_IDENTITY_VERIFICATION',
                    remaining_gaps=['CANDIDATE_CONTINUOUS_DAILY_RISK_NOT_SAVED','NEW_CHAIN_AGGREGATES_NOT_COMPUTED','SOURCE_PUBLICATION_AND_INDEPENDENT_READBACK','WORKBOOK_CELL_READBACK_AND_VISUAL_ACCEPTANCE'],
                    **dict.fromkeys(('source_bytes_authenticated','account_executed','risk_recomputed','chain_aggregates_computed','financial_recomputation_performed','point_in_time_verified','promotion_allowed','full_h_delivery_complete'),False))
    equal({key:value for key,value in supplement.items() if key!='tables'},expected,'Complete envelope and preserved original evidence')
    for index,table in enumerate(supplement['tables']):
        require(len(table['rows']) == progress[index],'Extra unverified rows')
    return dict(schema='MULTIDECISION_HOLDINGS_SUPPLEMENT_INSPECTION_V1',status='PASS',scope='ALL6_TABLES_SAVED_RAW_PROJECTION_NOT_RISK_DERIVATION',
                table_count=6,checked_cell_count=checked_cells,table_row_counts=[dict(name=name,count=progress[i]) for i,(name,_) in enumerate(HEADERS)],
                counts=counts,producer_called=False,risk_recomputed=False,source_bytes_authenticated=False,full_h_delivery_complete=False,promotion_allowed=False)
