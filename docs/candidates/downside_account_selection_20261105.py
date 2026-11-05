"""Draft same-call downside selection; no IO, account execution or production changes."""
from copy import deepcopy
from fractions import Fraction as F
import hashlib,json
from backtest.continuous_guided_account_decision import VERSION,REQUIRED_PINS
from data.current_research_capital_decision import decide_quantity_for_account
from backtest.research_exact_fast_guided_observed import enhanced_search
from backtest.downside_candidate_observer_integer_research import DownsideCandidateObserver
from backtest.capped_frontier_rerank_research import rerank as original_rerank,product_hash
from scripts.audit_capped_training_frontier import evaluate,capped
from backtest.research_exact_fraction_json import dumps as exact_dumps
from scripts.research.preflight_downside_frontier_20261105 import bounds,classify

def exact_hash(value):
    canonical=json.dumps(json.loads(exact_dumps(value)),sort_keys=True,separators=(',',':'),allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def evidence_binding(raw,stock_returns,qqq_reference,research_source_hashes):
    return dict(capital_decision_id=raw['decision_id'],capital_binding_sha256=exact_hash(raw['binding']),
        search_arguments_sha256=exact_hash(raw['binding']['search_arguments']),
        capital_source_hashes=deepcopy(raw['binding']['source_hashes']),
        research_source_hashes=deepcopy(research_source_hashes),
        stock_return_coordinates_sha256=exact_hash(stock_returns),qqq_coordinates_sha256=exact_hash(qqq_reference))


def decide_observed_for_account(*, stock_returns, qqq_reference, research_source_hashes, max_holdings, guard, **arguments):
    """Preserve V2 terminal semantics while reusing exact capital validation.

    Pins are caller-authenticated; this pure function does not read source files.
    The legacy core is pinned for the imported validator, never executed here.
    """
    if max_holdings != 10 or type(max_holdings) is not int:
        raise ValueError('FIXED_TEN_HOLDINGS_REQUIRED')
    if 'search' in arguments:
        raise ValueError('V2 search cannot be replaced')
    if any(path not in arguments['source_hashes'] for path in REQUIRED_PINS):
        raise ValueError('V2_METHOD_SOURCE_PINS_REQUIRED')
    observed = []
    sidecars = []

    def compatibility(**kwargs):
        observer = DownsideCandidateObserver(max_holdings=max_holdings, search_arguments=kwargs,
            stock_returns=stock_returns, qqq_reference=qqq_reference, max_risk_evaluations=10000)
        counts = {}
        class Guarded:
            def observe(self, quantities, *, phase, evaluation_index):
                guard()
                counts[phase] = counts.get(phase, 0) + 1
                observer.observe(quantities, phase=phase, evaluation_index=evaluation_index)
                guard()
        result = enhanced_search(candidate_observer=Guarded(), **kwargs)
        if result.get('selected') is None:
            raise ValueError('ORIGINAL_SEARCH_INCOMPLETE')
        observer.end_observation()
        sidecar = observer.finalize()
        extra = result['continuous_comparison']['exact_evaluations']
        if (counts.get('base') != result['objective_evaluations'] or
            counts.get('comparison') != extra['saved_unique'] + extra['new_unique'] or
            sidecar['coverage']['risk_evaluated'] != sidecar['coverage']['capped_unique']-sidecar['coverage']['over_holdings_limit']):
            raise ValueError('OBSERVED_CANDIDATE_COVERAGE_INCOMPLETE')
        sidecar['phase_counts'] = counts
        sidecars.append(sidecar)
        if result.get('method_version') != VERSION:
            raise ValueError('V2_METHOD_VERSION_MISMATCH')
        statuses = {
            'INSUFFICIENT_BUDGET_FOR_MANDATORY_COVERAGE': 'INSUFFICIENT_BUDGET_FOR_ALL_K_INITIALIZATION',
            'PER_K_SEARCH_STOPPED_WITH_UNUSED_BUDGET': 'LOCAL_NEIGHBORHOODS_EXHAUSTED',
            'BUDGET_STOPPED': 'BUDGET_STOPPED',
        }
        if result.get('status') not in statuses:
            raise ValueError('UNKNOWN_V2_TERMINAL_STATUS')
        observed.append(deepcopy(result))
        return dict(result, status=statuses[result['status']])

    result = decide_quantity_for_account(**arguments, search=compatibility)
    result['search_result'] = observed[0]  # Never publish the internal status translation.
    result['method'] = VERSION
    result['binding']['schema'] = 'CAPITAL_DECISION_CONTINUOUS_GUIDED_EXPERIMENT_V1'
    result['binding']['continuous_iterations'] = 32
    result['binding']['selection_method'] = VERSION
    identifier = hashlib.sha256(json.dumps(result['binding'], sort_keys=True,
        separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    result.update(decision_id=identifier, research_id=identifier[:24])
    result['limitations'].append('Original fair-k V2 plus 32 extra continuous proposal steps; not equal-budget, not production, not a drawdown guarantee.')
    sidecar=sidecars[0]
    sidecar['evidence_binding']=evidence_binding(result,stock_returns,qqq_reference,research_source_hashes)
    sidecar['integrity_sha256']=exact_hash(sidecar)
    result['downside_sidecar_sha256']=sidecar['integrity_sha256']
    return result, sidecar

def apply_downside_selection(*, raw, sidecar, stock_returns, qqq_reference, research_source_hashes):
    """Keep actual V27 cap/rerank incumbent on admissible product ties."""
    payload={k:v for k,v in sidecar.items() if k!='integrity_sha256'}
    if (sidecar.get('integrity_sha256')!=exact_hash(payload) or
        raw.get('downside_sidecar_sha256')!=sidecar.get('integrity_sha256')):
        raise ValueError('SIDECAR_INTEGRITY_MISMATCH')
    if sidecar.get('evidence_binding')!=evidence_binding(raw,stock_returns,qqq_reference,research_source_hashes):
        raise ValueError('SIDECAR_ACCOUNT_OR_COORDINATE_MISMATCH')
    original = original_rerank(raw)
    args = raw['binding']['search_arguments']
    incumbent = original['target_quantities']
    incumbent_score = evaluate({s:q for s,q in incumbent.items() if q}, args)
    if not sidecar['complete'] or sidecar['max_holdings'] != 10:
        raise ValueError('COMPLETE_TEN_HOLDINGS_SAME_CALL_DOMAIN_REQUIRED')
    days = list(qqq_reference)
    weights = {s:q*F(args['prices'][s])/F(args['entered_cash']) for s,q in incumbent.items() if q}
    values = [sum((w*F(stock_returns[s][d]) for s,w in weights.items()),F(0)) for d in days]
    reference = [F(qqq_reference[d]) for d in days]
    admitted,_,_ = classify(values,reference,bounds(reference))
    admitted = admitted and len(weights)<=10
    candidates = [sidecar['cash'],*sidecar['eligible_best_by_k'].values()]
    if any(record is None for record in candidates):raise ValueError('CASH_FALLBACK_REQUIRED')
    checked=[]
    for record in candidates:
        q=record['target_quantities'];score=evaluate(q,args)
        if (len(q)>10 or capped(q,args)!=q or len(q)!=record['actual_k'] or score['product']!=record['exact_product'] or
            score['notional']!=record['notional'] or score['residual_cash']!=record['residual_cash']):
            raise ValueError('SIDECAR_CANDIDATE_SCORE_MISMATCH')
        w={s:n*F(args['prices'][s])/F(args['entered_cash']) for s,n in q.items()}
        candidate_values=[sum((v*F(stock_returns[s][d]) for s,v in w.items()),F(0)) for d in days]
        passed,_,_=classify(candidate_values,reference,bounds(reference))
        if not passed:raise ValueError('SIDECAR_CANDIDATE_RISK_MISMATCH')
        checked.append((record,score))
    candidates=checked
    eligible = [(r,s) for r,s in candidates if not admitted or s['product']>incumbent_score['product']]
    if eligible:
        record,score = max(eligible,key=lambda pair:(pair[1]['product'],-pair[1]['notional'],tuple(sorted(pair[0]['target_quantities'].items()))))
        chosen=deepcopy(record['target_quantities'])
    else:
        chosen=deepcopy(incumbent);score=incumbent_score
    selected=deepcopy(original)
    selected.update(method='SAME_CALL_OBSERVED_DOWNSIDE_QQQ_V1',target_quantities=chosen,
        downside_audit=dict(incumbent='ACTUAL_V27_SAVED_FRONTIER_CAP50_RERANK',incumbent_admitted=admitted,
                           incumbent_product_sha256=product_hash(incumbent_score['product']),
                           selected_product_sha256=product_hash(score['product']),coverage=deepcopy(sidecar['coverage']),
                           tie_rule='ADMITTED_ACTUAL_V27_INCUMBENT_RETAINED_UNLESS_STRICT_PRODUCT_IMPROVEMENT',
                           holding_count_limit=10,source_authenticated=False))
    binding=dict(schema=selected['method'],original_rerank_decision_id=original['rerank_decision_id'],
                 target_quantities=chosen,downside_audit=selected['downside_audit'])
    selected['original_rerank_audit']=selected.pop('rerank_audit')
    selected['rerank_binding']=binding
    selected['rerank_decision_id']=hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return selected
