"""Isolated momentum sizing using the existing exact capital validation contract."""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
from backtest.momentum_equal_weight_target_research import build_target
from data.current_research_capital_decision import decide_quantity_for_account

ROSTER_PATH='tmp/cross_sectional_momentum_static_20261105/result.json'
ROSTER_SHA='5523b8d87e08a8946cf6d2e15aa28fb8f13b3608ef5bde012220f825979aaf3c'
CORE='backtest/momentum_equal_weight_target_research.py'

def need(ok,reason):
    if not ok:raise ValueError(reason)

def make_decider(*,root,window):
    root=Path(root);raw=(root/ROSTER_PATH).read_bytes()
    need(sha256(raw).hexdigest()==ROSTER_SHA,'FIXED_ROSTER_CHANGED')
    archive=json.loads(raw)
    pins={**archive['prior_expected_hashes_verified'],**archive['selection_artifact_hashes']}
    for path,digest in pins.items():need(sha256((root/path).read_bytes()).hexdigest()==digest,'ROSTER_SOURCE_CHANGED:'+path)
    need(len(archive['rows'])==67,'EXACT_67_ROSTERS')
    rosters={r['decision_date']:r for r in archive['rows'] if r['window']==window}
    need(len(rosters)=={'2021_2023':36,'2024_2026':31}[window],'WINDOW_ROSTERS')
    core_sha=sha256((root/CORE).read_bytes()).hexdigest()

    def decide(**arguments):
        day=arguments['decision_date'];need(day in rosters,'NO_FROZEN_ROSTER')
        need(arguments['source_hashes'].get(ROSTER_PATH)==ROSTER_SHA and arguments['source_hashes'].get(CORE)==core_sha,'MOMENTUM_SOURCE_PINS_REQUIRED')
        return decide_bound(roster=rosters[day],**arguments)
    return decide

def decide_bound(*,roster,decision_date,account_state,valuation_quotes,search_arguments,source_hashes):
    """Pure bound-row integration; production/replay must use make_decider."""
    need(roster['decision_date']==decision_date,'ROSTER_DATE')
    domain=search_arguments['metadata'];selected=roster['selected']
    need(len(selected)==10 and len({x['security_id'] for x in selected})==10 and len({x['issuer_id'] for x in selected})==10,'UNIQUE_TEN_ISSUERS')
    need(all(x['security_id'] in domain and domain[x['security_id']]['issuer_id']==x['issuer_id'] for x in selected),'ROSTER_LEGAL_DOMAIN_OR_ISSUER')
    need(F(str(search_arguments['fee_bps']))==0 and F(str(search_arguments['minimum_cash_buffer']))==0,'FIXED_ZERO_FEE_BUFFER')
    built=[]
    def deterministic_target(**validated):
        # This callback replaces search, not the existing input/accounting checks.
        result=build_target(roster=roster,decision_date=decision_date,investable_equity=validated['entered_cash'],nominal_prices=validated['prices'])
        built.append(result);equity=F(result['investable_equity'])
        quantities={s:q for s,q in result['target_quantities'].items() if q}
        notional=sum((F(str(validated['prices'][s]))*q for s,q in quantities.items()),F(0))
        return dict(decision_date=decision_date,entered_cash=str(equity),status='LOCAL_NEIGHBORHOODS_EXHAUSTED',selected=dict(quantities=quantities,notional=str(notional),fees='0',residual_cash=str(equity-notional),actual_k=len(quantities),actual_weights={s:str(F(str(validated['prices'][s]))*q/equity) for s,q in quantities.items()}))
    result=decide_quantity_for_account(decision_date=decision_date,account_state=account_state,valuation_quotes=valuation_quotes,search_arguments=search_arguments,source_hashes=source_hashes,search=deterministic_target)
    need(len(built)==1,'ONE_DETERMINISTIC_SIZING')
    result.update(target_quantities=deepcopy(built[0]['target_quantities']),momentum_target=built[0],roster=deepcopy(roster),core_calls=0,search_calls=0,target_sizing_calls=1,method='FROZEN_MOMENTUM_ROSTER_ACTUAL_TRADABLE_EQUITY')
    result['search_result']['status']='DETERMINISTIC_SIZING_NOT_SEARCH'
    return result
