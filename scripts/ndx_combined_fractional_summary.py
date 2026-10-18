"""Compact auditable summary of a complete fractional research date."""
import hashlib
import json
from pathlib import Path
from scripts import ndx_combined_fractional_date as combined
from backtest.ndx_dynamic_research_selector import select_research_lane
from backtest import ndx_joint_weight_runner as encoding

SELF = Path(__file__).resolve()
LOADED = hashlib.sha256(SELF.read_bytes()).hexdigest()
ROLES = ('RETURN', 'BAD_TAIL', 'DRAWDOWN', 'TARGET_ENVELOPE', 'USER_PREFERENCE')
ENCODING_PATH = str(Path(encoding.__file__).resolve())
REQUIRED_SOURCES = dict(combined._LOADED, **{str(SELF): LOADED,
    ENCODING_PATH: hashlib.sha256(Path(ENCODING_PATH).read_bytes()).hexdigest()})
ORIGINS = ('EQUAL_WEIGHT_BASE', 'NON_EQUAL_BASE', 'DELTA')


def _validate_summary(value):
    if (value['schema'] != 'ndx_combined_fractional_summary_v1'
            or any(value[key] is not False for key in ('promotion_allowed',
                'point_in_time_verified', 'saved_weights_are_execution_targets'))
            or value['whole_lot_status'] != 'NOT_EVALUATED'):
        raise ValueError('Research summary required')
    if set(value['counts']) != set(ORIGINS):
        raise ValueError('Exact origin counts required')
    for counts in value['counts'].values():
        if (set(counts) != {'planned', 'observed', 'evaluated'}
                or any(type(n) is not int or n < 0 for n in counts.values())
                or not counts['evaluated'] <= counts['observed'] <= counts['planned']):
            raise ValueError('Invalid origin counts')
    if (sum(c['planned'] for c in value['counts'].values()) != value['expected_date']['expected_task_count']
            or sum(c['observed'] for c in value['counts'].values()) != value['record_count']):
        raise ValueError('Summary denominator differs')
    if [r['policy_role'] for r in value['roles']] != list(ROLES):
        raise ValueError('Complete ordered roles required')
    for row in value['roles']:
        if (type(row['input_error_count']) is not int or row['input_error_count'] < 0
                or type(row['eligible_count']) is not int or not 0 <= row['eligible_count'] <= value['record_count']
                or row['status'] not in ('INPUT_INVALID', 'NO_DELTA', 'NO_ELIGIBLE_CANDIDATE', 'SELECTED')
                or (row['selected'] is not None) != (row['status'] == 'SELECTED')):
            raise ValueError('Invalid role summary')
    complete = all(r['input_error_count'] == 0 and r['status'] != 'INPUT_INVALID' for r in value['roles'])
    if (value['economic_inputs_complete'] is not complete or (complete and
            any(c['evaluated'] != c['planned'] for c in value['counts'].values()))):
        raise ValueError('Invalid summary completeness')
    if any(value['source_hashes'].get(path) != digest for path, digest in REQUIRED_SOURCES.items()):
        raise ValueError('Required summary source missing or changed')
    combined._check_sources(value['source_hashes'])


def summarize(date):
    sources = dict(date['source_hashes'])
    sources[str(SELF)] = LOADED
    if any(sources.get(path) != digest for path, digest in REQUIRED_SOURCES.items()):
        raise ValueError('Required computation source absent from bound inputs')
    for origin in ORIGINS:
        records = [row for row in date['records'] if row['origin'] == origin]
        if (date['counts'][origin]['observed'] != len(records)
                or date['counts'][origin]['evaluated'] != sum(r['status'] == 'EVALUATED' for r in records)):
            raise ValueError('Origin counts differ from actual records')
    combined._check_sources(sources)
    roles = []
    for role in ROLES:
        selection = select_research_lane(expected_dates=[date['expected_date']],
                                        records=date['records'], policy_role=role)['rows'][0]
        selected = selection['selected']
        reasons = {}
        for rejected in selection['rejections']:
            for reason in rejected['reasons']:
                reasons[reason] = reasons.get(reason, 0) + 1
        roles.append(dict(policy_role=role, status=selection['status'],
            eligible_count=selection['eligible_count'], rejection_reason_counts=reasons,
            input_error_count=len(selection['input_errors']),
            selected=None if selected is None else dict(task=selected['task'], origin=selected['origin'],
                eligibility=selected['eligibility'], fractional_metrics={key: selected['result'][key]
                    for key in ('return_p50','return_p10','max_drawdown_p50','max_drawdown_p90',
                        'paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent',
                        'paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent',
                        'return_p50_vs_012922','return_p10_vs_012922',
                        'max_drawdown_p50_vs_012922','max_drawdown_p90_vs_012922')})))
    record_digest = encoding._sha(encoding._normalize(date['records']))
    if date['economic_inputs_complete'] is not all(row['input_error_count'] == 0 for row in roles):
        raise ValueError('Summary completeness differs from selector evidence')
    combined._check_sources(sources)
    result = dict(schema='ndx_combined_fractional_summary_v1', expected_date=date['expected_date'],
        counts=date['counts'], records_sha256=record_digest, record_count=len(date['records']),
        roles=roles, economic_inputs_complete=date['economic_inputs_complete'],
        technology_scope_status=date['technology_scope_status'], source_hashes=sources,
        interpretation='OVERLAPPING_TRAINING_WINDOWS_NOT_CONTINUOUS_EXECUTION_OR_OOS',
        whole_lot_status='NOT_EVALUATED', saved_weights_are_execution_targets=False,
        point_in_time_verified=False, promotion_allowed=False)
    _validate_summary(result)
    return result


def save_new(summary, path):
    _validate_summary(summary)
    raw = (json.dumps(summary, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(raw)
    if destination.read_bytes() != raw or json.loads(raw) != summary:
        raise ValueError('Summary readback differs')
    combined._check_sources(summary['source_hashes'])
    return hashlib.sha256(raw).hexdigest()
