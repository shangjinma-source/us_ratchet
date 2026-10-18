"""Direct-artifact consumption inventory; no numerical model is invoked."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/cache/research/three_cell_corrected_paired_overlay_20260919_v2'
FIRST = [
('20230403','90aa907fef583cda6c787f2725444c21dabf601f2940f915c7bba011b41a10b6','2204ff0b9423853630e46eafa2cb1cfe9dd5b07985caadb9cfccadb21f451dad'),
('20230501','71ece37da8630c8d406aa9d314a15073c87006543df5d4832c056ce5311dade1','8297a7a4cd387be5bc6b5132552021e7a01ec695e618e893f9d93ac5e2eb5a69'),
('20230601','010086ff000de18f29d82598a57c48ef588bf3c239292eaaf3f157fbb04cd32e','c52988c125b2181a59bdebda50f4f4049ad40916b63e6d79da728df194698409'),
('20230703','31946405fda71dc6388a8c61893af347b682ef60087b702f2671404fa41415cd','a79e8be712d46bf68546ea0a19eebde07789e58af6add4dcb167cea97416fcb4'),
('20230801','781c724fd51c78cf6ab263909caf3c68494c10bab197f493cea98368f7f9c7ef','28bf580b0dcf079b18344894147ca87e9506a8422c460080df31da99ed349c96'),
('20230901','f083c3d10cdde1a5b1cc2d084eddd333cafc5c911ad659e2c249d5090439d598','5e070adcc85b83f9e7d167423a7cbdc674e4e2a15467b892a6db43dd81b76991')]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    sources = {str(Path(__file__).resolve()): sha(__file__)}
    def read(path, expected):
        path = Path(path).resolve()
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('External artifact SHA differs: ' + str(path))
        if str(path) in sources and sources[str(path)] != expected:
            raise ValueError('Direct source conflict')
        sources[str(path)] = expected
        return json.loads(raw)
    base = read(ROOT / 'data/cache/research/base_limited_overlay_20260919_v1/remaining12_completion_inventory_20260919.json',
                '35a8a6e7944cb2967e5aa6121196b08e3a88270fa9858a3097a35d8462b7d395')
    four = read(DEST / 'remaining_four_inventory_20260919.json', 'cccef58f42ccada3b9f766131cb4efd35c33e8d7559102a5103727a55e1a1198')
    entries = [dict(date=d, overlay_path=str(DEST / ('overlay_' + d + '.json')), overlay_sha256=o,
                    audit_path=str(DEST / ('diff_audit_' + d + '.json')), audit_sha256=a, mode='PAIRED_COMPLETE') for d, o, a in FIRST]
    entries += [dict(r, mode='PAIRED_COMPLETE') for r in four['dates']]
    entries += [dict(r, mode='BASE_REFERENCE_ZERO_PAIRED_TASKS_NO_NEW_MERGE') for r in base['dates'] if r['date'] >= '20240201']
    if len(entries) != 15 or [e['date'] for e in entries] != sorted({e['date'] for e in entries}):
        raise ValueError('Complete unique date inventory required')
    selected = read(ROOT / 'data/cache/research/delta_selected_input_20260912_v1/plan.json',
                    'f0ff0242f08dcb62ceb19d5650db811fe8d0d83741f7ecc995b6a3945cf15266')
    paired = read(ROOT / 'data/cache/research/delta_three_cell_paired_trace_20260912_v2/plan.json',
                  'fb2e514516123efe67dffb92821410ce2eb52d3e757494c4dfaf517c7ea9b330')
    def tasks(plan):
        return {(r['task']['selection_date'], r['task']['job_id']): r['task'] for d in plan['dates'] for r in d['tasks']}
    selected_tasks, paired_tasks = tasks(selected), tasks(paired)
    seen, pending_tasks, saved_paired, counts, dates = set(), {}, {}, Counter(), []
    paired_added = 0
    for entry in entries:
        overlay = read(entry['overlay_path'], entry['overlay_sha256'])
        audit = read(entry['audit_path'], entry['audit_sha256'])
        date = overlay['coordinate']['selection_date']
        if date.replace('-', '') != entry['date'] or audit['verified_source_hashes'].get(entry['overlay_path']) != entry['overlay_sha256']:
            raise ValueError('Date or independent audit binding differs')
        digest = hashlib.sha256(json.dumps(overlay['records'], sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if digest != overlay['records_sha256'] or any(overlay[k] is not False for k in ('historical_full_source_closure_verified',
            'point_in_time_verified', 'promotion_allowed', 'selection_performed')) or overlay['winner'] is not None:
            raise ValueError('Record digest or research flags differ')
        if entry['mode'] == 'PAIRED_COMPLETE':
            if overlay['schema'] != 'ndx_corrected_delta_paired_overlay_limited_drift_v2' or audit['complete_record_diff_verified'] is not True:
                raise ValueError('Complete paired overlay required')
            added = overlay['delta_paired_added']
            if added != audit['paired_replaced']:
                raise ValueError('Paired count differs')
            paired_added += added
        else:
            if (overlay['schema'] != 'ndx_corrected_base_overlay_limited_drift_v3' or audit['full_ordered_record_diff_verified'] is not True
                    or any(k[0] == date for k in paired_tasks)):
                raise ValueError('Zero-paired date must reference original completed BASE')
            added = 0
        local = Counter()
        for row in overlay['records']:
            key = (date, row['origin'], row['task']['job_id'])
            if key in seen:
                raise ValueError('Duplicate full record coordinate')
            seen.add(key)
            local[(row['origin'], row['status'])] += 1
            counts[(row['origin'], row['status'])] += 1
            taskkey = (date, row['task']['job_id'])
            if row['status'] == 'PENDING_NUMERICAL_DELTA':
                if row['result'] is not None or row['origin'] != 'DELTA':
                    raise ValueError('Unexpected pending result or origin')
                pending_tasks[taskkey] = row['task']
            elif row['status'] != 'AVAILABLE' or row['result'] is None:
                raise ValueError('Unknown record state')
            if row['overlay_mode'] == 'DELTA_PAIRED_COMPLETE_SUBQUEUE':
                if row['status'] != 'AVAILABLE':
                    raise ValueError('Consumed paired task is not available')
                saved_paired[taskkey] = row['task']
        available = sum(n for (_, s), n in local.items() if s == 'AVAILABLE')
        pending = sum(n for (_, s), n in local.items() if s == 'PENDING_NUMERICAL_DELTA')
        if available != overlay['available_count'] or pending != overlay['pending_count'] or available + pending != overlay['original_count']:
            raise ValueError('Full date counts differ')
        dates.append(dict(entry, original_count=overlay['original_count'], available=available, pending=pending, paired_added=added))
    if len(seen) != 351255 or pending_tasks != selected_tasks or len(pending_tasks) != 11254:
        raise ValueError('Exact pending selected task map differs')
    if saved_paired != paired_tasks or paired_added != 614:
        raise ValueError('Exact consumed paired task map differs')
    expected = {('EQUAL_WEIGHT_BASE', 'AVAILABLE'): 319473, ('NON_EQUAL_BASE', 'AVAILABLE'): 19548,
                ('DELTA', 'AVAILABLE'): 980, ('DELTA', 'PENDING_NUMERICAL_DELTA'): 11254}
    if dict(counts) != expected:
        raise ValueError('Global original track counts differ')
    return dict(schema='ndx_corrected_cohort_all15_consumption_inventory_20260919_v1', dates=dates, date_count=15,
        original_count=351255, available_count=340001, pending_count=11254, paired_tasks_completed_and_consumed=614,
        base_available=19548, equal_available=319473, delta_available=980, pending_exactly_hard_selected_plan_tasks=True,
        paired_exactly_hard_paired_plan_tasks=True, unique_coordinate_origin_task_records=True,
        verified_direct_artifact_hashes=sources, validation_scope='DIRECT_OVERLAYS_AND_DIFF_REPORTS_WITH_FULL_COUNTS_AND_TASK_MAPS',
        transitive_numerical_sources_rehashed_by_inventory=False, training_performed=False, no_fitter_or_evaluator_called=True,
        historical_full_source_closure_verified=False, point_in_time_verified=False, promotion_allowed=False, selection_performed=False, winner=None)


if __name__ == '__main__':
    result = build()
    for p, h in result['verified_direct_artifact_hashes'].items():
        if sha(p) != h:
            raise ValueError('Direct source changed before publication')
    output = DEST / 'all15_consumption_inventory_20260919.json'
    with output.open('x', encoding='utf8') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    for p, h in result['verified_direct_artifact_hashes'].items():
        if sha(p) != h:
            raise ValueError('Direct source changed after publication')
    print(json.dumps(dict(path=str(output), sha256=sha(output), available=result['available_count'], pending=result['pending_count'])))
