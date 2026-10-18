"""Conditional dated account inputs only; no fitting, raw decoding or execution."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
import math
import re

SCHEMA='DATED_CONDITIONAL_ACCOUNT_INPUTS_V1'
FLAGS=dict.fromkeys(('account_executed','fit_performed','source_bytes_authenticated','split_evidence_authenticated','historical_identity_verified','provider_binding_verified','point_in_time_verified','promotion_allowed','legal_training_input_admitted','execution_authorized','untouched_holdout','future_independent_oos','corporate_action_completeness_verified','dividend_cash_flows_modelled','total_return_modelled'),False)
PARAMETERS=dict(fit_days=126,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55,shrinkage_intensity=.35,turnover_anchor_strength=.25)
UNIT='SAVED_CHANNEL_SPLIT_ADJUSTED_PRICES_CONDITIONALLY_REVERSED_BY_ALL_LATER_ORDINARY_EVENTS_NOT_CERTIFIED'
EVENT_KEYS={'security_id','session','new_shares','old_shares','source_url','evidence_sha256'}


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def reference(value):
    require(type(value) is dict and set(value)=={'path','sha256'} and type(value['path']) is str and value['path'],'Exact external reference')
    require(type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['sha256']) is not None,'Reference SHA')


def rational(value,*,positive=False,allow_float=False):
    require(type(value) in ((str,int,float) if allow_float else (str,int)),'Explicit finite numeric encoding; no bool')
    if type(value) is float:require(math.isfinite(value),'Finite saved float')
    try:out=Fraction(str(value))
    except (ValueError,ZeroDivisionError):raise ValueError('Invalid exact number')
    require(out>0 if positive else out>=0,'Positive price/nonnegative weight')
    return out


def engine_key(sid):
    require(type(sid) is str and sid.startswith('security:') and re.fullmatch('[A-Za-z0-9_:]+',sid),'Explicit SID')
    return 'SID_'+sid[len('security:'):].replace(':','_').upper()


def assemble_dated_account_inputs(*,task,fit_result,task_reference,fit_reference,candidate_channels_by_security,incumbent_securities,incumbent_channels_by_security,channel_references,split_evidence_by_security):
    for value in (task_reference,fit_reference):reference(value)
    identity=task['numerical_identity'];selected=identity['selected']
    require(identity['schema']=='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1' and identity['cutoff']=='2026-03-20' and identity['requested_previous_target_weights'] is None,'Only new03-20 None-prior task')
    require(task['numerical_task_id']==digest(identity) and task['location_id']==digest(task['location_identity']),'Task identity digest')
    require(task['location_identity']['schema']=='DATED_FIXED_CONSTITUENT_TASK_LOCATION_V1','Dated location')
    require(type(selected) is dict and list(selected)==sorted(selected) and len(selected)==identity['holding_count'] and identity['parameters']['fit_days']==126,'Canonical selected/fitting126')
    require(all(set(row)=={'ticker','issuer_id','risk_chain'} and all(type(v) is str and v for v in row.values()) for row in selected.values()),'Explicit selected three fields')
    require(len({r['issuer_id'] for r in selected.values()})==len(selected),'Selected duplicate issuer')
    require(fit_result['schema']=='ndx_dynamic_cutoff_refit_research_v2' and fit_result['cutoff']==identity['cutoff'] and fit_result['fit_data_sha256']==identity['fit_data_sha256'] and fit_result['weight_spec']==identity['weight_spec'],'Returned dated fit binding')
    require(fit_result['previous_target_weights']=={} and digest(fit_result['source_hashes'])==identity['fitter_source_fingerprint'],'Actual prior and source closure')
    require(set(fit_result['targets'])==set(selected),'All selected targets including zero weights')
    require(digest(identity['parameters'])==digest(PARAMETERS),'Frozen original eight parameters')
    targets={}
    for sid,row in selected.items():
        target=fit_result['targets'][sid]
        require(target['ticker']==row['ticker'] and target['issuer_id']==row['issuer_id'],'Returned selected coordinates')
        rational(target['target_weight'],allow_float=True);targets[sid]=deepcopy(target)
    require(abs(sum((rational(t['target_weight'],allow_float=True) for t in targets.values()),Fraction())-1)<=Fraction(1,10**9),'Original target simplex tolerance')
    require(type(incumbent_securities) is list and len(incumbent_securities)==8,'Original8 explicit ordered definition')
    control={}
    for row in incumbent_securities:
        require(all(type(row[k]) is str and row[k] for k in ('security_id','ticker','issuer_id','risk_chain')),'Original control coordinates')
        sid=row['security_id'];require(sid not in control,'Duplicate original control SID');rational(row['target_weight'],allow_float=True);control[sid]=deepcopy(row)
    require(math.isclose(sum(float(r['target_weight']) for r in control.values()),1.,rel_tol=0.,abs_tol=1e-12),'Original control sum tolerance; no normalization')
    require(len({r['issuer_id'] for r in control.values()})==8 and sum((rational(r['target_weight'],allow_float=True) for r in control.values()),Fraction())>0,'Control issuer/positive original weight mass')
    require(set(candidate_channels_by_security)==set(selected) and set(incumbent_channels_by_security)==set(control),'Exact channels per account')
    union=set(selected)|set(control)
    require(set(channel_references)==union and set(split_evidence_by_security)==union,'Complete perSID references and explicit event lists')
    for value in channel_references.values():
        require(type(value) is dict and set(value)=={'path','sha256','json_pointer'} and type(value['json_pointer']) is str and value['json_pointer'].startswith('/'),'Explicit channel document pointer')
        reference({k:value[k] for k in ('path','sha256')})
    keymap={s:engine_key(s) for s in sorted(union)};require(len(set(keymap.values()))==len(union),'Engine key collision')
    common_calendar=None
    def account(coordinates,channels,weights,role):
        nonlocal common_calendar
        order=list(coordinates) if role=='incumbent' else sorted(coordinates)
        columns=[keymap[s] for s in order];price_rows={};evidence={};actions=[];preserved={}
        for sid in order:
            channel=channels[sid]
            require(channel['ticker']==coordinates[sid]['ticker'] and channel['status']=='CONDITIONAL_NUMERIC_RESULT' and channel['conditional_reconstruction_performed'] is True,'Saved usable nominal channel')
            require(channel['provider_price_unit_assumption']==UNIT,'Must use reconstructed nominal not adjusted price')
            full=channel['calendar'];require(len(full)==253 and full==sorted(set(full)) and all(date.fromisoformat(d).isoformat()==d for d in full),'Complete253 source calendar')
            require(channel['training_freeze_close_date']==full[126]=='2026-03-20' and full[127]=='2026-03-23' and full[-1]=='2026-09-21','Freeze/execution/end clock')
            rows=channel['quote_rows'];require(len(rows)==253 and [r['session'] for r in rows]==full,'No dropped or reordered quotes')
            calendar=full[126:]
            if common_calendar is None:common_calendar=calendar
            require(calendar==common_calendar,'Candidate/control exact common127 calendar')
            converted=[]
            for index,row in enumerate(rows[126:],126):
                values={}
                for field in ('open','close'):
                    value=rational(row['nominal_'+field+'_exact'],positive=True);number=float(value)
                    require(math.isfinite(number) and number>0,'float64 price boundary')
                    values[field]=dict(exact=str(value),value=number,float_hex=number.hex(),source_reference=deepcopy(channel_references[sid]),json_pointer=channel_references[sid]['json_pointer']+f'/quote_rows/{index}/nominal_{field}_exact')
                converted.append(dict(session=row['session'],**values))
            price_rows[sid]=converted
            policies=[p for p in channel['event_policies'] if calendar[0]<p['session']<=calendar[-1]]
            supplied=split_evidence_by_security[sid];require(type(supplied) is list and len(supplied)==len(policies),'Every evaluation split needs explicit evidence')
            require(len({p['session'] for p in policies})==len(policies),'Duplicate policy day')
            for policy,binding in zip(policies,supplied):
                require(set(binding)=={'event','policy_reference'},'Exact event and policy pointer binding')
                event=binding['event'];require(set(event)==EVENT_KEYS,'Engine split schema')
                pointer=binding['policy_reference'];require(type(pointer) is dict and set(pointer)=={'path','sha256','json_pointer'} and type(pointer['json_pointer']) is str and pointer['json_pointer'].startswith('/'),'Original policy pointer')
                reference({k:pointer[k] for k in ('path','sha256')})
                require(policy['kind']=='ORDINARY_SPLIT' and event['security_id']==sid and event['session']==policy['session'] and event['session'] in calendar,'Ordinary split identity/date')
                for key,pkey in (('new_shares','numerator'),('old_shares','denominator')):
                    require(type(event[key]) is int and event[key]>0 and type(policy[pkey]) is int and policy[pkey]>0 and event[key]==policy[pkey],'Exact integer split ratio')
                require(type(event['source_url']) is str and event['source_url'].startswith(('https://','http://')) and type(event['evidence_sha256']) is str and re.fullmatch('[0-9a-f]{64}',event['evidence_sha256']) is not None,'Saved event source declaration required, not authenticated')
                actions.append(deepcopy(event))
            evidence[sid]=deepcopy(supplied);preserved[sid]=deepcopy(channel)
        schedule_targets={s:dict(ticker=keymap[s],issuer_id=coordinates[s]['issuer_id'],target_weight=weights[s]) for s in order}
        matrices={field:dict(index=common_calendar,columns=columns,data=[[price_rows[s][i][field]['value'] for s in order] for i in range(127)]) for field in ('open','close')}
        return dict(role=role,engine_input_compatibility=dict(status=('BLOCKED_NONPOSITIVE_TARGET' if any(rational(weights[s],allow_float=True)==0 for s in order) else 'REQUIRES_FROZEN_VALIDATION'),nonpositive_target_security_ids=[s for s in order if rational(weights[s],allow_float=True)==0]),candidate_normalization_required_by_engine=(role=='candidate'),engine_input_status=('BLOCKED_ZERO_TARGET_WEIGHT' if any(rational(weights[s],allow_float=True)==0 for s in order) else 'STRUCTURALLY_ASSEMBLED_CONDITIONAL_INPUT'),engine_dispatch_blockers=(['FROZEN_ENGINE_REQUIRES_STRICTLY_POSITIVE_TARGET_WEIGHTS'] if any(rational(weights[s],allow_float=True)==0 for s in order) else []),engine_weight_semantics=('FROZEN_CANDIDATE_NORMALIZES_POSITIVE_TARGET_WEIGHTS' if role=='candidate' else 'CONTROL_RESTORES_ORIGINAL_WEIGHTS_AFTER_POSITIVE_TARGET_NORMALIZATION'),original_security_order=order,original_ticker_by_security={s:coordinates[s]['ticker'] for s in order},engine_ticker_by_security={s:keymap[s] for s in order},matrices=matrices,exact_quote_conversion_evidence=price_rows,
            schedule=[dict(decision_date=common_calendar[0],execution_date=common_calendar[1],targets=schedule_targets)],risk_chains_by_decision={common_calendar[0]:{s:coordinates[s]['risk_chain'] for s in order}},corporate_actions=actions,split_evidence_preserved=evidence,complete_channels_preserved=preserved,
            risk_parameters={k:v for k,v in PARAMETERS.items() if k not in ('fit_days','shrinkage_intensity','turnover_anchor_strength')},initial_cash_usd=25000,minimum_cash_buffer_usd=100,transaction_cost_bps=10,valuation_end_date=common_calendar[-1],external_cashflows=[],identity_events=[],initial_holdings={},initial_point_included=True,weights_normalized=False,
            split_application_order='BEFORE_OPEN_MARK_AND_EXECUTION_BY_FROZEN_ENGINE;PENDING_BASKET_CANCELLED_ON_SPLIT',nominal_prices_adjusted_again=False,risk_observation_gates_orders=(role=='candidate'),**FLAGS)
    candidate=account(selected,candidate_channels_by_security,{s:targets[s]['target_weight'] for s in selected},'candidate')
    incumbent=account(control,incumbent_channels_by_security,{s:control[s]['target_weight'] for s in control},'incumbent')
    for sid in set(selected)&set(control):
        require(candidate['exact_quote_conversion_evidence'][sid]==incumbent['exact_quote_conversion_evidence'][sid],'Overlapping exact quotes differ')
    return dict(schema=SCHEMA,calendar=common_calendar,valuation_point_count=127,return_interval_count=126,candidate=candidate,incumbent=incumbent,engine_security_keys=keymap,
        original_task=deepcopy(task),original_fit_result=deepcopy(fit_result),task_reference=deepcopy(task_reference),fit_reference=deepcopy(fit_reference),original_incumbent_definition=deepcopy(incumbent_securities),
        original_candidate_coordinates=deepcopy(selected),candidate_risk_declaration_preserved=deepcopy(fit_result.get('declared_constraint_checks')),fit_returns_or_weights_recomputed=False,caller_evidence_not_authenticated=True,
        limitations=['LATE_POOL_AND_COMPOSITION_SELECTION','EVALUATION_WINDOW_PREVIOUSLY_USED_BY_OLD_FITS','NO_DIVIDEND_CASHFLOW_OR_TOTAL_RETURN','SOURCE_URL_AND_HASH_REQUIRE_EXTERNAL_WRAPPER_AUTHENTICATION','ORIGINAL_CONTROL_WEIGHTS_NOT_NORMALIZED'],**FLAGS)
