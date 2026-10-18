"""Fixed-host full77 training bank; descriptive numbers, never qualified cash actions."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import stat
import time
import types

_ROOT = Path(__file__).resolve().parents[1]
_READER = (_ROOT / 'backtest/ndx_variable_cardinality_new_cash_source_binding_research.py',
           '1d8d6197d837d2f1e45b1b999e48e7b543a8920db19418d9d2c003786c2f67e5')
_MOMENTS = (_ROOT / 'backtest/ndx_full_pool_training_moments_research.py',
            '447400d0ced6bb9b0198ccc506b63a65eba57d3bbd111f682ec6b612c84ba71d')
_CONTRACTS = (
    (_ROOT / 'tmp/full_pool_training_matrix_binding_design_20261009_v1/manifest.json',
     'ce873dfbf969724761b6ec90afa6426889d8dd608c97f4f1150f5c8a71e14e2b'),
    (_ROOT / 'tmp/full_pool_training_matrix_budget_addendum_20261009_v2/manifest.json',
     '43619f639badce79fecbdfde5086dab77a547e85bf9e00c01f1661ceb6d90bfe'))
EXACT_MODEL = 'EXACT_SPLIT_RETURN_GRAM_DIAGONAL_SHRINK_REFERENCE_V1'
LEGACY_MODEL = 'LEGACY_FLOAT64_SAMPLE_DIAGONAL_SHRINK_DESCRIPTION_V1'


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _read_regular(path):
    for item in (path,) + tuple(path.parents):
        info = item.lstat()
        _require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 1024,
                 'Reparse/symlink source forbidden')
    _require(path.is_file(), 'Regular source file required')
    return path.read_bytes()


_LOADED_CODE_SHA = _sha(_read_regular(Path(__file__)))


def _load_fixed(reference):
    path, expected = reference
    raw = _read_regular(path)
    _require(_sha(raw) == expected, 'Fixed source bytes changed: ' + str(path))
    module = types.ModuleType('_fixed_training_' + expected[:12])
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def _parameters(include_covariance, include_bench, budget, model, resume):
    if resume is not None:
        raise NotImplementedError('Resume is not supported in the first version')
    _require(type(include_covariance) is bool and type(include_bench) is bool, 'Options must be bool')
    _require(type(model) is str and model in (EXACT_MODEL, LEGACY_MODEL), 'Unknown covariance model')
    if budget is not None:
        _require(type(budget) is int and budget >= 0, 'work_budget must be nonnegative integer, not bool')
    if include_covariance:
        _require(budget is not None, 'Explicit finite work_budget required for covariance')
        if model == LEGACY_MODEL:
            raise NotImplementedError('Legacy float covariance estimation is not implemented in the first stage')
    else:
        _require(budget in (None, 0), 'Positive budget requires include_covariance=True')


def _matrix(source_columns, start, stop, dates, ids):
    return dict(model_id=EXACT_MODEL, ordered_security_ids=list(ids), training_dates=list(dates),
                shape=[stop - start, len(ids)],
                cells=[[c['original_channel']['return_rows'][r]['split_only_return_exact']
                        for c in source_columns] for r in range(start, stop)])


def _estimate_unique(unique, work_budget, helper):
    """One shared canonical atomic prefix; later matrices cannot spend a stopped prefix."""
    remaining, spent, counts, stopped = work_budget, 0, {}, False
    for item in unique:
        assigned = 0 if stopped else remaining
        item['moments'] = helper.prepare_exact_training_moments(matrix=item['matrix'], work_budget=assigned)
        work = item['moments']['work']
        remaining -= work['spent']
        spent += work['spent']
        if work['pending_tasks']:
            stopped = True
        for key, value in work['actual_primitive_counts'].items():
            counts[key] = counts.get(key, 0) + value
    return remaining, spent, counts


def _build_bank(source_facts, *, include_covariance, work_budget, helper):
    """Private construction from the fixed reader only; public pure access confers no binding."""
    _require(source_facts['schema'] == 'CONDITIONAL_FULL_POOL_SOURCE_FACTS_V1', 'Source facts schema')
    _require([source_facts[k] for k in ('conditional_security_count', 'conditional_issuer_count',
                                     'observed_provenance_count')] == [77, 76, 101], 'Whole original pool')
    _require(source_facts['qualified_inventory'] is None and source_facts['qualified_denominator'] is None,
             'No qualified pool')
    _require(len(source_facts['source_checks']) == 10 and all(v is False for v in source_facts['permissions'].values()),
             'Ten source gaps and authority false')
    columns = source_facts['channel_facts']
    ids = source_facts['matrix_layout']['ordered_security_ids']
    _require(len(columns) == len(ids) == 77 and len(set(ids)) == 77, 'Whole77 order')
    calendar = columns[0]['original_channel']['calendar']
    for c, sid in zip(columns, ids):
        channel = c['original_channel']
        _require(c['coordinate']['security_id'] == sid and channel['calendar'] == calendar, 'SID/calendar association')
        _require(len(channel['return_rows']) == 609 and len(channel['quote_rows']) == 610,
                 'Complete column rows')
        for g, row in enumerate(channel['return_rows']):
            _require(row['previous_session'] == calendar[g] and row['session'] == calendar[g + 1], 'Return calendar')
    windows, unique, groups = [], [], {}
    ready = blocked = checked = 0
    train_sid_blocked, eval_sid_blocked = {}, {}
    for di, decision in enumerate(columns[0]['original_channel']['decisions']):
        _require(len(decision['windows']) == 13, 'Thirteen windows')
        for wi, original in enumerate(decision['windows']):
            a, b = original['training_return_index_start'], original['training_return_index_stop']
            e, f = original['evaluation_return_index_start'], original['evaluation_return_index_stop']
            _require(b - a == f - e == 126 and e == b and 0 <= a < b <= f <= 609,
                     '126 training/evaluation half-open indices')
            dates = calendar[a + 1:b + 1]
            _require(original['training_price_predecessor'] == calendar[a]
                     and original['training_freeze_close'] == calendar[b], 'Train price endpoints')
            train_missing, eval_missing, statuses = [], [], []
            for ci, col in enumerate(columns):
                d = col['original_channel']['decisions'][di]
                w = d['windows'][wi]
                _require(d['cutoff'] == decision['cutoff'] and w['window_index'] == wi, 'Original window association')
                for key in ('training_return_index_start', 'training_return_index_stop',
                            'evaluation_return_index_start', 'evaluation_return_index_stop'):
                    _require(w[key] == original[key], 'All77 same indices')
                rows = col['original_channel']['return_rows']
                tm = [g for g in range(a, b) if rows[g]['split_only_return_exact'] is None]
                em = [g for g in range(e, f) if rows[g]['split_only_return_exact'] is None]
                statuses.append(w['status'])
                if tm:
                    train_missing.append(dict(column=ci, security_id=ids[ci], global_return_indices=tm))
                    ticker = col['coordinate']['ticker']
                    train_sid_blocked[ticker] = train_sid_blocked.get(ticker, 0) + 1
                if em:
                    eval_missing.append(dict(column=ci, security_id=ids[ci], global_return_indices=em))
                    ticker = col['coordinate']['ticker']
                    eval_sid_blocked[ticker] = eval_sid_blocked.get(ticker, 0) + 1
                checked += b - a
            payload = _matrix(columns, a, b, dates, ids)
            encoded = _canonical(payload)
            digest = _sha(encoded)
            candidates = groups.setdefault(digest, [])
            group = next((i for i in candidates if unique[i]['matrix'] == payload), None)
            if group is None:
                group = len(unique)
                candidates.append(group)
                unique.append(dict(matrix_sha256=digest, matrix=payload, window_ordinals=[],
                                   numerical_status='SOURCE_BLOCKED' if train_missing else 'NUMERIC_READY_NOT_SOURCE_QUALIFIED',
                                   moments=None))
            unique[group]['window_ordinals'].append(len(windows))
            ready += not bool(train_missing)
            blocked += bool(train_missing)
            windows.append(dict(window_ordinal=len(windows), cutoff=decision['cutoff'], window_index=wi,
                                shape=[126, 77], training_start=a, training_stop=b,
                                training_dates=list(dates), training_price_predecessor=calendar[a],
                                training_freeze_close=calendar[b], evaluation_start=e, evaluation_stop=f,
                                training_blocked_sid_rows=train_missing,
                                evaluation_diagnostic=dict(blocked_sid_rows=eval_missing, numeric_values_used_in_training=False),
                                original_window_status_by_column=statuses, unique_matrix_index=group,
                                training_numeric_payload_sha256=digest,
                                lineage_manifest_sha256=_sha(_canonical(dict(
                                    window_ordinal=len(windows), sources=source_facts['consumed_source_hashes'],
                                    cutoff=decision['cutoff'], original_indices=[a,b,e,f], model=EXACT_MODEL))),
                                formal_training_input_ready=False))
    _require(len(windows) == 78 and checked == 756756 and ready == 27 and blocked == 51, 'Whole training domain')
    _require(train_sid_blocked == {'WDC': 51, 'LRCX': 27} and eval_sid_blocked == {'WDC': 15, 'LRCX': 1},
             'Original training and independent evaluation blockers')
    remaining = work_budget or 0
    spent = 0
    estimation_counts = {}
    if include_covariance:
        remaining, spent, estimation_counts = _estimate_unique(unique, remaining, helper)
    facts = dict(schema='FULL_CONDITIONAL_POOL_TRAINING_BANK_V1',
                 status='CONDITIONAL_TRAINING_NUMBERS_REAL_SOURCE_BLOCKED',
                 source_facts={k:v for k,v in source_facts.items() if k != 'channel_facts'},
                 source_columns=columns, windows=windows, unique_training_matrices=unique,
                 source_cell_mapping=dict(global_return_index='windows[w].training_start+r',
                                          return_pointer='/return_rows/{g}', quote_pointers=['/quote_rows/{g}', '/quote_rows/{g+1}'],
                                          raw_lookup='source_columns[c].original_channel.quote_rows[g].raw_row_index plus raw_required_scope_numeric_tokens'),
                 coverage=dict(securities=77, issuers=76, original_provenance=101, windows=78,
                               sid_window_cells=6006, training_cell_coordinates=checked,
                               training_numeric_ready_windows=ready, blocked_training_windows=blocked,
                               unique_numeric_ready_matrices=sum(x['numerical_status'] != 'SOURCE_BLOCKED' for x in unique),
                               training_blocked_sid_windows=train_sid_blocked, evaluation_blocked_sid_windows=eval_sid_blocked),
                 covariance_models=[dict(id=EXACT_MODEL, ddof=1, shrinkage='7/20', unit='DAILY_STOCK_RETURN_VARIANCE'),
                                    dict(id=LEGACY_MODEL, status='NOT_IMPLEMENTED_IN_FIRST_STAGE', shrinkage='.35 nativefloat',
                                         input='Original return numeric tokens at explicit float boundary; not exact')],
                 work=dict(requested=work_budget, spent=spent, unused=remaining,
                           actual_primitive_counts=estimation_counts, source_reader_calls=1,
                           matrix_cell_checks=checked, source_column_row_checks=77*609,
                           unique_matrix_count=len(unique), covariance_estimation_enabled=include_covariance,
                           scope='NUMERICAL_MOMENT_PRIMITIVES_ONLY_NOT_TOTAL_TIME_OR_IO',
                           independent_certificate_recheck_tasks=0, resume_replay_tasks=0,
                           reader_internal_io_operations_not_instrumented=None,
                           reader_whole_channel_replays_reported=77),
                 qualified_inventory=None, qualified_denominator=None, current_account=None,
                 current_new_money=None, plan_rows=[], real_joint_objective='UNREGISTERED',
                 causal_action_rule='UNREGISTERED', thirteen_cohort_prior_cash='SOURCE_BLOCKED',
                 permissions=deepcopy(source_facts['permissions']))
    known_shared = {
        'bridge': str(_ROOT / 'data/cache/research/new_cutoff_event_policy_20260923_v1/bridge.json'),
        'timezone_new_york': r'D:\python\Lib\site-packages\tzdata\zoneinfo\America\New_York',
    }
    facts['shared_lineage_references'] = {
        role: dict(path=path, sha256=source_facts['consumed_source_hashes'][path])
        for role, path in known_shared.items()}
    return facts


def get_training_cell(bank_facts, *, window_ordinal, row, column):
    """Detached no-IO access to every compact cell, no caller source authentication."""
    for value, bound in ((window_ordinal, 78), (row, 126), (column, 77)):
        _require(type(value) is int and 0 <= value < bound, 'Cell index out of range/not integer')
    window = bank_facts['windows'][window_ordinal]
    source = bank_facts['source_columns'][column]
    g = window['training_start'] + row
    doc = source['original_channel']
    ret = doc['return_rows'][g]
    pointer = f'/return_rows/{g}/split_only_return_float'
    token = source['original_numeric_tokens'].get(pointer)
    legacy = dict(original_value=ret['split_only_return_float'], original_token=token, float_hex=None)
    if ret['split_only_return_float'] is not None:
        _require(token is not None, 'Original float token required')
        legacy['float_hex'] = float(token['original_lexeme']).hex()
    quotes = []
    for index in (g, g + 1):
        q = doc['quote_rows'][index]
        ri = q['raw_row_index']
        prefix = f'/chart/result/0/indicators/quote/0/'
        raw_tokens = {field: source['raw_required_scope_numeric_tokens'].get(prefix + f'{field}/{ri}')
                      for field in ('open', 'high', 'low', 'close', 'volume')} if ri is not None else {}
        quotes.append(dict(pointer=f'/quote_rows/{index}', original_quote=q, raw_tokens=raw_tokens))
    return deepcopy(dict(security_id=source['coordinate']['security_id'], global_return_index=g,
                         return_pointer=f'/return_rows/{g}', original_return=ret,
                         exact=ret['split_only_return_exact'], legacy_float_boundary=legacy,
                         price_endpoints=quotes, source_reference=source['source_reference'],
                         raw_reference=source['raw_reference'], receipt_reference=source['receipt_reference'],
                         shared_lineage_references=bank_facts['shared_lineage_references'],
                         source_authentication=False))


def read_source_bound_training_bank(*, include_covariance=False, include_saved_dual_benchmarks=False,
                                    work_budget=None, covariance_model=EXACT_MODEL, resume_state=None):
    """Fresh fixed whole-source read once; no true77 moment estimation is implicit."""
    _parameters(include_covariance, include_saved_dual_benchmarks, work_budget, covariance_model, resume_state)
    started = time.perf_counter()
    refs = (_READER, _MOMENTS) + _CONTRACTS + ((Path(__file__), _LOADED_CODE_SHA),)
    for path, expected in refs:
        _require(_sha(_read_regular(path)) == expected, 'Fixed source bytes changed: ' + str(path))
    reader = _load_fixed(_READER)
    helper = _load_fixed(_MOMENTS)
    saved = reader.read_conditional_full_pool_sources(include_saved_dual_benchmarks=include_saved_dual_benchmarks)
    facts = _build_bank(saved['facts'], include_covariance=include_covariance, work_budget=work_budget, helper=helper)
    guard_work = dict(calls=0, code_files_checked=0, code_bytes_checked=0,
                      forwarded_source_guard_calls=0, fixed_source_hash_bytes_per_forwarded_call=sum(
                          Path(path).stat().st_size for path in saved['facts']['consumed_source_hashes']))

    def final_guard():
        for path, expected in refs:
            raw = _read_regular(path)
            _require(_sha(raw) == expected, 'Fixed source bytes changed: ' + str(path))
            guard_work['code_files_checked'] += 1
            guard_work['code_bytes_checked'] += len(raw)
        saved['final_guard']()
        guard_work['calls'] += 1
        guard_work['forwarded_source_guard_calls'] += 1
        return deepcopy(dict(status='PASS_FIXED_SOURCE_AND_MODEL_GUARD_NOT_AUTHORIZATION', **guard_work))

    first_guard = final_guard()
    facts['implementation_references'] = [dict(path=str(path), sha256=expected) for path, expected in refs]
    facts['work']['initial_final_guard'] = first_guard
    facts['work']['elapsed_seconds'] = time.perf_counter() - started
    return dict(facts=facts, final_guard=final_guard)
