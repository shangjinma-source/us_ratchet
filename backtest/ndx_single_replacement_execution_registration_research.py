"""Structural full-domain execution plan; no evaluator, IO or authority."""
from copy import deepcopy
import hashlib
import json

EVALUATOR_SHA = '4303ead0a9d57d1bb95a4b6c563c707894a71eadec3c881bd082be3be5f1d767'
FLAGS = dict.fromkeys(('source_bytes_authenticated', 'dispatch_authorized', 'risk_evaluated',
    'point_in_time_verified', 'economic_winner_selected', 'account_executed'), False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def integer(value):
    require(type(value) is int and value >= 0, 'Exact nonnegative integer')
    return value


def reference(value):
    require(type(value) is dict and set(value) == {'path', 'sha256'}, 'Exact reference')
    require(type(value['path']) is str and bool(value['path']), 'Reference path')
    h = value['sha256']
    require(type(h) is str and len(h) == 64 and all(c in '0123456789abcdef' for c in h), 'SHA256')
    return deepcopy(value)


def build_execution_registration(*, prepared, preparation_reference,
        preparation_audit_reference, evaluator_reference, shard_size=512):
    require(type(prepared) is dict and set(prepared) == {'document', 'content_sha256'}, 'Prepared envelope')
    d = prepared['document']
    require(digest(d) == prepared['content_sha256'], 'Prepared content hash')
    require(d['schema'] == 'SINGLE_REPLACEMENT_DOMAIN_PREPARATION_V1', 'Domain schema')
    require(type(shard_size) is int and 1 <= shard_size <= 10000, 'Bounded engineering shard size')
    refs = dict(preparation=reference(preparation_reference), audit=reference(preparation_audit_reference),
                evaluator=reference(evaluator_reference))
    require(refs['evaluator']['sha256'] == EVALUATOR_SHA, 'Frozen single replacement evaluator')
    cases = d['cases']; expected_ids = d['action_contract']['expected_scenario_ids']
    require(type(cases) is list and len(cases) == integer(d['scenario_count']) == len(expected_ids), 'Full scenario inventory')
    require(len(set(expected_ids)) == len(expected_ids), 'Unique scenarios')
    cursor = financial = excluded = pair_count = 0
    case_index = []
    for ci, c in enumerate(cases):
        require(type(c['scenario_index']) is int and c['scenario_index'] == ci and c['scenario_id'] == expected_ids[ci], 'Original scenario order')
        require(integer(c['first_global_ordinal']) == cursor, 'Case partition start')
        require(digest(c['identity']) == c['identity_sha256'], 'Scenario identity')
        start = cursor; cf = ce = 0
        require(len(c['pairs']) == integer(c['pair_count']), 'Pair denominator')
        for pi, p in enumerate(c['pairs']):
            require(type(p['pair_index']) is int and p['pair_index'] == pi, 'Pair order')
            require(integer(p['first_global_ordinal']) == cursor, 'Pair partition start')
            n = integer(p['enumerable_quantity_count']); f = integer(p['financial_quantity_count'])
            conflicts = p['issuer_exclusion_certificate']['conflicts']
            require(n == (0 if conflicts else f), 'Full retained or excluded quantity domain')
            require(type(p['quantity_min']) is int and p['quantity_min'] == 1 and integer(p['quantity_max']) == f, 'Complete quantity interval')
            cursor += n; cf += f; ce += f-n; pair_count += 1
        require(integer(c['integer_count']) == cursor-start and integer(c['financial_integer_count_before_issuer']) == cf
                and integer(c['structurally_excluded_integer_count']) == ce, 'Case full partition')
        case_index.append(dict(scenario_index=ci, scenario_id=c['scenario_id'], start=start, stop=cursor,
                               pair_count=len(c['pairs']), financial_count=cf, structurally_excluded_count=ce))
        financial += cf; excluded += ce
    require(cursor == integer(d['integer_count']) and pair_count == integer(d['pair_count'])
            and financial == integer(d['financial_integer_count_before_issuer'])
            and excluded == integer(d['structurally_excluded_integer_count']) and financial == cursor+excluded, 'Full domain partition')
    shards = []
    for i, start in enumerate(range(0, cursor, shard_size)):
        identity = dict(schema='SINGLE_REPLACEMENT_SHARD_V1', preparation_sha256=prepared['content_sha256'],
                        ordinal=i, start=start, stop=min(start+shard_size, cursor))
        shards.append(dict(identity=identity, shard_id=digest(identity)))
    body = dict(schema='SINGLE_REPLACEMENT_EXECUTION_REGISTRATION_V1',
                status='STRUCTURAL_FULL_DOMAIN_PLAN_NOT_DISPATCH_PERMISSION', references=refs,
                prepared_content_sha256=prepared['content_sha256'], scenario_count=len(cases),
                pair_count=pair_count, integer_count=cursor, financial_integer_count_before_issuer=financial,
                structurally_excluded_integer_count=excluded, cases=case_index, shards=shards,
                shard_size=shard_size, shard_count=len(shards), scope=d['scope'],
                evaluation_api='PRIVATE_VALIDATED_PROJECT_THEN_EVALUATE_ONE',
                public_batch_evaluation_called=False, automatic_retry_allowed=False, **FLAGS)
    return dict(document=body, content_sha256=digest(body))


def summarize_execution_prefix(*, registration, terminal_rows, unresolved_ordinal=None):
    require(digest(registration['document']) == registration['content_sha256'], 'Registration hash')
    d = registration['document']; total = integer(d['integer_count'])
    require(type(terminal_rows) is list and len(terminal_rows) <= total, 'Bounded terminal prefix')
    counts = dict.fromkeys(('FEASIBLE', 'INFEASIBLE', 'EVALUATION_EXCEPTION', 'VALIDATION_FAILURE'), 0)
    for i, row in enumerate(terminal_rows):
        require(type(row['global_ordinal']) is int and row['global_ordinal'] == i, 'Contiguous original prefix')
        outcome = row['outcome']; require(outcome in counts, 'Explicit terminal outcome')
        if outcome in ('EVALUATION_EXCEPTION', 'VALIDATION_FAILURE'):
            require(i == len(terminal_rows)-1 and unresolved_ordinal is None, 'Technical terminal stops prefix')
        counts[outcome] += 1
    n = len(terminal_rows)
    if unresolved_ordinal is not None:
        require(type(unresolved_ordinal) is int and unresolved_ordinal == n < total, 'Only next original slot unresolved')
    pending_start = n + int(unresolved_ordinal is not None)
    return dict(full_integer_count=total, terminal_count=n, outcome_counts=counts,
                unresolved_ordinal=unresolved_ordinal, undispatched_start=pending_start,
                undispatched_stop=total, undispatched_count=total-pending_start,
                automatic_retry_allowed=False, **FLAGS)
