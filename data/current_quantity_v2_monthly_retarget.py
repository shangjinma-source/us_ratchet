"""Pure monthly equity retarget; source declarations are not authentication."""
from copy import deepcopy
from fractions import Fraction
from zoneinfo import ZoneInfo
from data.current_quantity_v2_difference_plan import (
    build_account_difference_plan,validate_execution_inputs,allocate_differences,require,stamp,number)
from data.current_quantity_v2_paper_ledger import digest

SCOPE='MONTHLY_CURRENT_QUOTE_ALLOCATION'


def active_proposal(ledger):
    return ledger.get('active_monthly_acceptance',ledger['acceptance'])['proposal']


def active_entry_policy(ledger):
    old=active_proposal(ledger)
    frozen=old.get('causal_inputs',{}).get('frozen_execution_package',{})
    docs=frozen.get('documents',{})
    if 'pullback_policy' in docs or 'pullback_proofs' in docs:
        from data.current_quantity_v2_current_cash_continuation import frozen_pullback_policy
        return frozen_pullback_policy(old)
    return deepcopy(old.get('causal_inputs',{}).get('pullback_policy'))


def require_supported_monthly_entry_policy(ledger,policy=None):
    require(active_entry_policy(ledger)==policy,'PULLBACK_MONTHLY_POLICY_REQUIRED')


def apply_monthly_pullback_limits(limits,references,policy,now,*,sell_only=frozenset()):
    """Pure declaration validation after raw-proof replay by the source bridge."""
    if policy is None:
        require(all('pullback' not in ref for ref in references.values()),'UNAUTHORIZED_MONTHLY_PULLBACK_POLICY')
        return limits
    from data.current_quantity_v2_pullback_entry import VERSION, digest as policy_digest
    require(type(policy)is dict and set(policy)=={'schema','status','rebound_fraction','minimum_discount','maximum_age_seconds'}
            and policy['schema']=='V2_PULLBACK_EXECUTION_POLICY_V1'
            and policy['status']=='EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED','INVALID_PULLBACK_POLICY')
    ratio=number(policy['rebound_fraction']);discount=number(policy['minimum_discount'])
    require(0<ratio<1 and 0<discount<1 and type(policy['maximum_age_seconds'])is int
            and 0<policy['maximum_age_seconds']<=120,'INVALID_PULLBACK_POLICY')
    expected=dict(version=VERSION,rebound_fraction=str(ratio),minimum_discount=str(discount),
                  maximum_age_seconds=policy['maximum_age_seconds'])
    require(set(sell_only)<=set(references),'INVALID_SELL_ONLY_DOMAIN')
    result=deepcopy(limits)
    for sid,ref in references.items():
        if sid in sell_only and 'pullback' not in ref:continue
        candidate=ref.get('pullback');last=number(ref['last_price'])
        require(type(candidate)is dict and candidate.get('execution_policy')==policy
                and candidate.get('schema')==VERSION and candidate.get('policy')==expected,
                'PULLBACK_MONTHLY_POLICY_REQUIRED')
        binding=candidate['binding']
        require(binding['security_id']==sid and binding['ticker']==ref['ticker']
                and binding['session']==ref['session'] and binding['policy_id']==policy_digest(expected)
                and binding['currency']=='USD' and binding['price_basis']==ref['price_basis'],
                'MONTHLY_PULLBACK_BINDING_MISMATCH')
        require(number(candidate['last_price'])==last and stamp(now)<stamp(candidate['reference_valid_until'])
                and stamp(ref['valid_until'])<=stamp(candidate['reference_valid_until']),
                'MONTHLY_PULLBACK_REFERENCE_INVALID')
        low=number(candidate['observed_session_low']);require(low>0,'MONTHLY_PULLBACK_REFERENCE_INVALID')
        anchor=min(low,last);ceiling=min(anchor+ratio*(last-anchor),last*(1-discount))
        prior=candidate['prior_cap']
        if prior is not None:
            require(prior['binding']==binding and stamp(ref['session_open'])<=stamp(prior['observed_at'])
                    <=stamp(ref['captured_at']),'MONTHLY_PULLBACK_PRIOR_INVALID')
            cap=number(prior['limit_price']);require(cap>0 and (cap*100).denominator==1,'MONTHLY_PULLBACK_PRIOR_INVALID')
            ceiling=min(ceiling,cap)
        buy=Fraction(ceiling*100//1,100)
        require(buy>0 and buy<last and buy==number(candidate['limit_price']),'MONTHLY_PULLBACK_LIMIT_INVALID')
        result[sid]=(buy,limits[sid][1])
    return result


def validate_held_continuity(ledger,a,now):
    old=active_proposal(ledger)
    bridges=a['held_unit_continuity']
    positive={sid for sid,q in ledger['shares'].items() if q}
    require(set(bridges)==positive,'HELD_CONTINUITY_DOMAIN_REQUIRED')
    oldinputs=old['causal_inputs'];oldsecurities=old.get('securities',oldinputs.get('securities'))
    bounded_reviews=[]
    for sid in positive:
        bridge=bridges[sid];ref=a['execution_references'][sid]
        if old.get('target_scope')=='NEW_CASH_CURRENT_QUOTE_ALLOCATION':
            prior=next(row for row in old['rows'] if row['security_id']==sid)
        else:prior=oldinputs['execution_references'][sid]
        bounded=bridge.get('status')=='NO_KNOWN_UNIT_CHANGE_UNDER_BOUNDED_PUBLIC_REVIEW'
        require(set(bridge)-({'bounded_evidence'} if bounded else set())=={'prior_revision','security_id','prior_reference_source_hashes',
            'reference_source_hashes','prior_active_proposal_id','prior_price_basis','price_basis','security_class','covered_from','covered_through','reviewed_at','status','source_references'},'HELD_CONTINUITY_FIELDS')
        require(all(a['securities'][sid].get(k)==oldsecurities[sid].get(k) for k in ('ticker','issuer_id'))
            and bridge['security_class']==oldsecurities[sid].get('security_class')
            and a['securities'][sid].get('security_class',bridge['security_class'])==bridge['security_class']
            and bridge['security_id']==sid
            and bridge['prior_revision']==ledger['revision'] and bridge['prior_active_proposal_id']==old['proposal_id']
            and bridge['prior_price_basis']==('PROVIDER_CURRENT_REGULAR_NOMINAL_QUOTE' if old.get('target_scope')=='NEW_CASH_CURRENT_QUOTE_ALLOCATION' else oldinputs['execution_references'][sid]['price_basis'])
            and bridge['price_basis']==ref['price_basis']
            and bridge['prior_reference_source_hashes']==prior['source_hashes']
            and bridge['reference_source_hashes']==ref['source_hashes']
            and (bounded or bridge['status']=='NO_UNPROCESSED_ACTIONS')
            and stamp(bridge['covered_from'])<=stamp(prior['captured_at'])
            and stamp(ref['captured_at'])<=stamp(bridge['covered_through'])<=stamp(bridge['reviewed_at'])<=stamp(now)
            and bridge['source_references'] and all(p in a['source_hashes'] for p in bridge['source_references'])
            and all(a['source_hashes'].get(p)==h for p,h in prior['source_hashes'].items()),'HELD_UNIT_CONTINUITY_REQUIRED')
        if bounded:
            from data.current_quantity_v2_monthly_bounded_review import replay_monthly_review
            bounded_reviews.append(replay_monthly_review(bridge,security=a['securities'][sid],current=ref,
                source_hashes=a['source_hashes'],now=now,origin={k:prior[k] for k in ('captured_at','source_hashes')},held_capital_decision=a['capital_decision']))
    return bounded_reviews


def proposal_for_month(ledger,proposal_inputs,now):
    policy=proposal_inputs.get('pullback_policy')
    require_supported_monthly_entry_policy(ledger,policy)
    require(all(o['closed'] in ('FILLED','CANCELLED','EXPIRED') for o in ledger['orders'].values())
        and number(ledger['reserved_cash'])==0 and not any(ledger['reserved_shares'].values()),'PRIOR_ORDERS_OPEN')
    a=deepcopy(proposal_inputs);a['now']=stamp(now).isoformat()
    a.pop('pullback_policy',None)
    derived_review=a.pop('account_review',None)
    if derived_review is not None:
        from data.current_quantity_v2_paper_review import validate_review_ledger_binding
        from data.current_quantity_v2_paper_chain import validate_derived_review_sources
        validate_review_ledger_binding(derived_review,ledger,now)
        validate_derived_review_sources(derived_review,a['source_hashes'])
    require(a['target_scope']=='ACCOUNT_EQUITY_TARGET','FULL_ACCOUNT_SCOPE_REQUIRED')
    account=a['account_state'];old=active_proposal(ledger)
    oldmonth=old.get('target_month') or old['causal_inputs']['target_mandate']['target_month']
    month=a['target_mandate']['target_month']
    require(month>oldmonth and month==stamp(now).astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m'),'NEW_TARGET_MONTH_REQUIRED')
    previous_decision=old['causal_inputs']['capital_decision']
    require(a['capital_decision']['decision_date']>previous_decision['decision_date']
        and a['capital_decision']['decision_id']!=previous_decision['decision_id'],'NEW_MONTHLY_DECISION_REQUIRED')
    observed=max(stamp(ledger['last_recorded_at']),stamp(ledger['last_effective_at']))
    require(account['account_id']==ledger['account_id'] and account['revision']==ledger['revision']
        and number(account['cash'])==number(ledger['cash']) and account['shares']==ledger['shares']
        and observed<=stamp(account['observed_at'])<=stamp(now),'MONTHLY_ACCOUNT_MISMATCH')
    bounded_reviews=validate_held_continuity(ledger,a,now)
    bridges=a.pop('held_unit_continuity')
    validated=build_account_difference_plan(**a)
    require(validated['status']=='READY',validated.get('reason','INVALID_MONTHLY_INPUT'))
    decision=a['capital_decision'];historical=decision['target_quantities']
    limits,deadlines=validate_execution_inputs(**{k:a[k] for k in ('capital_decision','account_state','securities',
        'execution_references','unit_continuity','source_hashes')},targets=historical,now=stamp(now))
    limits=apply_monthly_pullback_limits(limits,a['execution_references'],policy,now,
        sell_only={sid for sid,q in ledger['shares'].items() if q>0 and historical.get(sid,0)==0})
    allocations={sid:number(decision['binding']['search_arguments']['prices'][sid])*q for sid,q in historical.items()}
    targets={sid:int(value/limits[sid][0]) if value else 0 for sid,value in allocations.items()}
    require(sum(allocations.values())<=number(decision['investable_equity']),'ALLOCATION_EXCEEDS_EQUITY')
    orders,waiting,reserved,factor=allocate_differences(targets=targets,held=ledger['shares'],cash=number(ledger['cash']),limits=limits)
    a['held_unit_continuity']=bridges
    if derived_review is not None:a['account_review']=derived_review
    if policy is not None:a['pullback_policy']=deepcopy(policy)
    binding=dict(prior_revision=ledger['revision'],recorded_fees=ledger['recorded_fees'],causal_inputs=a,
        target_quantities=targets,historical_target_quantities=deepcopy(historical))
    result=dict(schema='V2_MONTHLY_RETARGET_PROPOSAL_V1',target_scope=SCOPE,status='READY',proposal_id=digest(binding),
        execution_target_id=digest(dict(scope=SCOPE,**binding)),binding=binding,causal_inputs=a,
        account_id=ledger['account_id'],capital_decision_id=decision['decision_id'],research_id=decision['research_id'],
        target_month=month,target_quantities=targets,historical_target_quantities=deepcopy(historical),
        frozen_dollar_allocations_exact={s:str(v) for s,v in allocations.items()},orders=orders,wait_cash=waiting,
        actual_cash=ledger['cash'],reserved_buy_cash=str(reserved),remaining_cash=str(number(ledger['cash'])-reserved),
        buy_allocation_factor=str(factor),unfilled_sell_proceeds='0',
        reference_valid_until=min(deadlines).isoformat() if deadlines else None,
        action='ORDERS' if orders else 'WAIT_CASH' if waiting else 'NO_ACTION',research_only=True,
        execution_blocked=True,real_account=False,source_authenticated=False,source_bytes_verified=False)

    for sid,unit in a['unit_continuity'].items():
        if unit.get('status')=='NO_KNOWN_UNIT_CHANGE_UNDER_BOUNDED_PUBLIC_REVIEW':
            from data.current_quantity_v2_monthly_bounded_review import replay_monthly_review
            bounded_reviews.append(replay_monthly_review(unit,security=a['securities'][sid],current=a['execution_references'][sid],
                source_hashes=a['source_hashes'],now=now,capital_decision=decision))
    if bounded_reviews:
        result['unit_review']=dict(bounded_reviews[0],limited_name_coverage=any(r['limited_name_coverage'] for r in bounded_reviews),
            limitations=list(dict.fromkeys(v for r in bounded_reviews for v in r['limitations'])))
    return result



def build_monthly_retarget(state,*,proposal_inputs,now):
    from data.current_quantity_v2_paper_chain import review_chain,validate_derived_review
    verified=review_chain(state)
    validate_derived_review(verified,proposal_inputs.get('account_review'),now,verified_prefix=True)
    return proposal_for_month(verified['ledger'],proposal_inputs,now)
