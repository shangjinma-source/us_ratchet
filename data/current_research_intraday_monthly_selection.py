"""Pure monthly TOP1 bridge bound to verified live paper capital, not a trade."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
from hashlib import sha256
import json
import re
from zoneinfo import ZoneInfo
from data.current_research_monthly_retarget_capital import build_monthly_retarget_capital
from data.current_research_monthly_policy import route_monthly_research_policy
from data.current_research_intraday_buy_plan import _require,_time
from backtest.return_priority_monthly_top1_selector import select_top1_quantities,VERSION


def build_intraday_monthly_top1_selection(state,*,capital,capital_inputs,training_input,
        target_month,selection_calendar,source_hashes,now):
    flags=dict(research_only=True,execution_blocked=True,activated=False,account_mutated=False,
        source_authenticated=False,global_optimum_established=False,forecast_return=None,
        method=VERSION,core_calls=0,selector_calls=0)
    try:
        now=_time(now)
        _require('state' not in capital_inputs and 'now' not in capital_inputs,'CAPITAL_ARGUMENT_SCHEMA')
        rebuilt=build_monthly_retarget_capital(state,now=now,**capital_inputs)
        _require(rebuilt['status']=='READY' and rebuilt==capital,'CAPITAL_RECONSTRUCTION_MISMATCH')
        money=capital['capital'];equity=Fraction(money['investable_equity'])
        _require(equity>0,'POSITIVE_SELECTION_CAPITAL_REQUIRED')
        _require(isinstance(source_hashes,dict) and source_hashes and all(isinstance(p,str) and p and isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h) for p,h in source_hashes.items()),'SOURCE_PINS_REQUIRED')
        for p,h in money['source_hashes'].items():_require(source_hashes.get(p)==h,'CAPITAL_SOURCE_PIN_MISMATCH')
        selector_path='backtest/return_priority_monthly_top1_selector.py'
        _require(selector_path in source_hashes,'SELECTOR_SOURCE_PIN_REQUIRED')
        data=training_input;args=deepcopy(data['search_arguments']);decision=args['decision_date']
        _require(date.fromisoformat(decision).isoformat()==decision,'INVALID_SELECTION_DATE')
        active=money['market_session']['date']
        current_month=_time(state['acceptance']['accepted_at']).astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
        route=route_monthly_research_policy(decision_date=decision,active_date=active,calendar=selection_calendar,current_target_month=current_month)
        _require(route['action']=='RESELECT' and route['target_month']==target_month,'NEW_MONTH_RESELECTION_REQUIRED')
        _require(_time(data['decision_session_close_at'])<=now and _time(data['decision_session_close_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()==decision,'IMMATURE_SELECTION_SESSION')
        dates=data['training_dates']
        _require(isinstance(dates,list) and len(dates)==253 and dates==sorted(set(dates)) and dates[-1]==decision
                 and all(date.fromisoformat(d).isoformat()==d for d in dates),'253_COMMON_TRAINING_DATES_REQUIRED')
        _require(args['scenario_dates']==[dates[i] for i in range(21,253,21)] and data['scenario_start_dates']==[dates[i] for i in range(0,252,21)],'TWELVE_NONOVERLAPPING_21_SESSION_SCENARIOS_REQUIRED')
        domain=set(args['prices']);metadata=args['metadata']
        _require(domain and domain==set(metadata)==set(data['eligible_security_ids']) and len(data['eligible_security_ids'])==len(domain),'ELIGIBLE_DOMAIN_MISMATCH')
        universe=data['universe_security_ids'];excluded=data['exclusions']
        _require(isinstance(excluded,dict) and all(isinstance(reason,str) and reason for reason in excluded.values())
                 and isinstance(universe,list) and len(universe)==len(set(universe))
                 and domain.isdisjoint(excluded) and domain|set(excluded)==set(universe),'FULL_CANDIDATE_COVERAGE_REQUIRED')
        _require(data['admission_status']=='REVIEWED_CONDITIONAL_COMPLETE_DOMAIN'
                 and isinstance(data['training_coordinate_policy'],str) and data['training_coordinate_policy']
                 and data['decision_price_date']==decision and isinstance(data['decision_price_basis'],str) and data['decision_price_basis'],'EXPLICIT_TRAINING_ADMISSION_REQUIRED')
        refs=data['source_references'];_require(isinstance(refs,list) and refs and all(p in source_hashes for p in refs),'TRAINING_SOURCE_NOT_PINNED')
        _require(set(data['source_hashes'])<=set(source_hashes) and all(source_hashes[p]==h for p,h in data['source_hashes'].items()) and data['source_hashes'],'TRAINING_SOURCE_PIN_MISMATCH')
        for sid,row in metadata.items():
            _require(isinstance(sid,str) and sid and isinstance(row.get('issuer_id'),str) and row['issuer_id'] and isinstance(row.get('ticker'),str) and re.fullmatch('[A-Z0-9][A-Z0-9.-]{0,14}',row['ticker']),'CANDIDATE_IDENTITY_REQUIRED')
        _require(Fraction(str(args['fee_bps']))==0 and Fraction(str(args['minimum_cash_buffer']))==0,'ZERO_COMMISSION_BUFFER_MODEL_REQUIRED')
        # Prices retain the mature decision's declared coordinate. Current marks
        # size capital only and never replace candidate training/cost prices.
        args['entered_cash']=str(equity)
        result=select_top1_quantities(**args)
        flags['selector_calls']=1
        _require(result['status']=='SELECTOR_COMPLETE','SELECTOR_INCOMPLETE')
        binding=dict(schema='INTRADAY_MONTHLY_TOP1_SELECTION_BRIDGE_V1',method=VERSION,
            account_id=money['initial_capital_identity']['account_id'],account_revision=money['account_revision'],
            capital_binding_id=capital['capital_binding_id'],capital=deepcopy(capital),training_input=deepcopy(data),
            actual_selector_arguments=args,source_hashes=deepcopy(source_hashes),target_month=target_month,
            route=route,selection_calendar=deepcopy(selection_calendar),selected_at=now.isoformat(),selector_result=result)
        digest=sha256(json.dumps(binding,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        return dict(flags,status='READY',research_id=digest[:24],decision_id=digest,binding=binding,
            capital_binding_id=capital['capital_binding_id'],historical_reference_target_quantities=deepcopy(result['selected']['quantities']),
            selected_capital_allocation={result['ranked_security_id']:'1'},
            selected_security_id=result['ranked_security_id'],target_month=target_month,
            investable_equity=str(equity),buy_cash_limit=money['buy_cash_limit'],unfilled_sell_proceeds_available='0',
            target_quantity_basis='MATURE_DECISION_PRICE_NOT_INTRADAY_LIMIT',
            limitations=['TOP1 ranks one-stock training products; it does not establish all-k optimality or future returns.',
                'Domain completeness and price-coordinate admissions are pinned caller declarations, not independently authenticated here.',
                'No order, sale proceeds, capital injection or month activation is created. Persist this result before any downstream use.'])
    except (ValueError,KeyError,TypeError,ZeroDivisionError) as error:
        return dict(flags,status='BLOCKED',reason=str(error),research_id=None)
