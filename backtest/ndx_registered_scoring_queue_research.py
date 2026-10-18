"""Engineering batches of the entire registered scoring domain; never evaluate."""
import hashlib
import json
import re
from copy import deepcopy
from collections import Counter

CUTOFFS = ('2026-03-31', '2026-04-30', '2026-05-29', '2026-06-30', '2026-07-31', '2026-08-31')
MODES = ('STRICT_SAME_SESSION_FX', 'BACKWARD_LATEST_VALID_FX')
SPECS = ('equal_weight', 'constrained_fixed_shrinkage', 'constrained_fixed_shrinkage_turnover_anchor')
JOBS_PER_SHARD = 32


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def exact(left, right, message):
    require(digest(left) == digest(right), message)


def build_registered_scoring_queue(*, budget_plan, budget_reference):
    require(type(budget_reference) is dict and set(budget_reference) == {'path', 'sha256'}, 'Exact budget reference')
    require(type(budget_reference['path']) is str and bool(budget_reference['path'])
            and type(budget_reference['sha256']) is str
            and re.fullmatch('[a-f0-9]{64}', budget_reference['sha256']) is not None, 'Budget path and SHA')
    require(budget_plan['schema'] == 'MULTIDECISION_SCORING_BUDGET_PLAN_V1', 'Registered budget schema')
    require(budget_plan['content_sha256'] == digest({k: v for k, v in budget_plan.items() if k != 'content_sha256'}),
            'Complete saved budget digest')
    for key in ('score_computed', 'fit_performed', 'account_executed', 'execution_authorized',
                'point_in_time_verified', 'complete_ndx_universe_verified', 'promotion_allowed'):
        require(budget_plan[key] is False, 'Original budget authority preserved')
    universe = budget_plan['full_universe_preserved']
    require(len(universe) == 77 and len({s['security_id'] for s in universe}) == 77
            and len({s['issuer_id'] for s in universe}) == 76, 'Full 77/76 inventory')
    inventory = {s['security_id']: s for s in universe}
    multiplicities = {}
    for security in universe:
        issuer = security['issuer_id']
        multiplicities[issuer] = multiplicities.get(issuer, 0) + 1
    coefficients = [1]
    for count in multiplicities.values():
        coefficients.append(0)
        for k in range(len(coefficients) - 1, 0, -1):
            coefficients[k] += count * coefficients[k - 1]
    rows = budget_plan['rows']
    require(len(rows) == 6 and [r['cutoff'] for r in rows] == list(CUTOFFS), 'Six original decisions')
    logical = []
    executable = []
    blocked = []
    coordinates = []
    seen = set()
    for decision_index, row in enumerate(rows):
        require(row['sampling']['complete'] is True, 'Incomplete point selection cannot be dispatched')
        exact(row['universe_preserved'], universe, 'Full row inventory')
        coverage = row['domain_coverage']
        require(type(coverage) is list and len(coverage) == 76, 'All 76 cardinality denominators')
        for k, card in enumerate(coverage, 1):
            require(type(card['k']) is int and card['k'] == k, 'Ordered full cardinality range')
            parts = ('qualification_excluded_combination_count', 'necessary_bound_excluded_combination_count',
                     'selected_combination_count', 'unsearched_eligible_after_bounds')
            for key in (*parts, 'full_inventory_combination_count', 'full_three_spec_task_denominator'):
                require(type(card[key]) is int and card[key] >= 0, 'Exact nonnegative domain counts')
            require(card['full_inventory_combination_count'] == coefficients[k]
                    == sum(card[key] for key in parts)
                    and card['full_three_spec_task_denominator'] == 3 * coefficients[k],
                    'Full issuer polynomial and four-way domain partition')
        positions = row['sampling']['positions']
        require(type(positions) is list and len(positions) == 544, 'Full registered 544 positions')
        selected_by_k = Counter(position['k'] for position in positions)
        for card in coverage:
            require(card['selected_combination_count'] == selected_by_k[card['k']],
                    'Per-cardinality selected count equals actual positions')
        require([m['mode'] for m in row['mode_plans']] == list(MODES), 'Both FX modes in original order')
        expected_semantics = [(p['security_ids'], spec) for p in positions for spec in SPECS]
        require(len({(tuple(sids), spec) for sids, spec in expected_semantics}) == 1632, 'Unique full position/spec set')
        for mode_index, mode in enumerate(row['mode_plans']):
            require(mode['source_preserved']['mode'] == mode['mode'], 'Source evidence target mode')
            require(type(mode['source_preserved']['complete_thirteen_windows']) is bool, 'Explicit source completeness')
            state = 'PLANNED_NOT_ATTEMPTED' if mode['source_preserved']['complete_thirteen_windows'] else 'SOURCE_BLOCKED'
            require(mode['status'] == state and mode['score_dispatch_authorized'] is False, 'Unchanged registered mode state')
            jobs = mode['tasks']
            require(type(mode['task_count']) is int and mode['task_count'] == len(jobs) == 1632, 'Complete mode task count')
            start = len(logical)
            for task_index, (job, semantics) in enumerate(zip(jobs, expected_semantics)):
                identity = job['identity']
                require(job['job_id'] == digest(identity) and job['job_id'] not in seen, 'Unique registered identity hash')
                seen.add(job['job_id'])
                require(identity['cutoff'] == row['cutoff'] and identity['fx_mode'] == mode['mode']
                        and job['status'] == state, 'Job coordinate/source status')
                exact((identity['security_ids'], identity['weight_spec']), semantics, 'Original composition/spec order')
                exact(job['position'], positions[task_index // 3], 'Original sampling position')
                sids = identity['security_ids']
                require(type(sids) is list and len(sids) == len(set(sids))
                        and all(sid in inventory for sid in sids), 'Unique registered SIDs')
                require(sids == sorted(sids, key=lambda sid: (inventory[sid]['issuer_id'], sid)),
                        'Canonical issuer-index column order')
                require(len({inventory[sid]['issuer_id'] for sid in sids}) == len(sids), 'One security per issuer')
                require(type(job['position']['k']) is int and job['position']['k'] == len(sids), 'Exact holding count')
                descriptor = dict(logical_ordinal=len(logical), decision_index=decision_index,
                                  mode_index=mode_index, task_index=task_index, job_id=job['job_id'],
                                  job_pointer=f'/plan/rows/{decision_index}/mode_plans/{mode_index}/tasks/{task_index}',
                                  cutoff=row['cutoff'], fx_mode=mode['mode'], holding_count=len(sids),
                                  weight_spec=identity['weight_spec'], registered_status=state,
                                  execution_ordinal=None if state == 'SOURCE_BLOCKED' else len(executable))
                logical.append(descriptor)
                if state == 'SOURCE_BLOCKED':
                    blocked.append(descriptor['logical_ordinal'])
                else:
                    executable.append(descriptor['logical_ordinal'])
            coordinates.append(dict(decision_index=decision_index, mode_index=mode_index,
                                    cutoff=row['cutoff'], fx_mode=mode['mode'], source_status=state,
                                    logical_start=start, logical_stop=len(logical), registered_task_count=len(jobs),
                                    source_preserved=deepcopy(mode['source_preserved']),
                                    all_k_domain_preserved=deepcopy(row['domain_coverage'])))
    shards = []
    for start in range(0, len(executable), JOBS_PER_SHARD):
        ordinals = executable[start:start + JOBS_PER_SHARD]
        shard = dict(shard_index=len(shards), execution_start=start, execution_stop=start + len(ordinals),
                     logical_ordinals=ordinals, job_ids=[logical[i]['job_id'] for i in ordinals])
        shard['content_sha256'] = digest(shard)
        shards.append(shard)
    require(len(logical) == 19584 and len(blocked) + len(executable) == len(logical), 'Whole logical domain partition')
    result = dict(schema='REGISTERED_SCORING_FULL_QUEUE_V1', budget_reference=deepcopy(budget_reference),
                  budget_content_sha256=budget_plan['content_sha256'], logical_jobs=logical,
                  logical_job_count=len(logical), executable_logical_ordinals=executable,
                  executable_job_count=len(executable), source_blocked_logical_ordinals=blocked,
                  source_blocked_job_count=len(blocked), coordinates=coordinates, shards=shards,
                  shard_count=len(shards), maximum_jobs_per_shard=JOBS_PER_SHARD,
                  first_executable_job=None if not executable else deepcopy(logical[executable[0]]),
                  reuse_requires_explicit_external_completed_audit=True,
                  first_probe_removed_from_registered_domain=False, source_bytes_authenticated=False,
                  shard_size_is_engineering_only=True, economic_results_used_for_ordering=False,
                  score_computed=False, fit_performed=False, account_executed=False,
                  automatic_retry_allowed=False, execution_authorized=False,
                  point_in_time_verified=False, promotion_allowed=False)
    result['content_sha256'] = digest(result)
    return result
