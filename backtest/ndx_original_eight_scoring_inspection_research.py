"""Independent saved-return projection inspection; no producer or raw quote calls."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib,json,math
import numpy as np
from importlib.metadata import version

ORDER=['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG']
CUTOFFS=['2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31']
FALSE=('source_bytes_authenticated','historical_identity_verified','historical_risk_verified','point_in_time_verified','execution_authorized','promotion_allowed','fit_performed','score_computed','raw_reconstructed','account_simulated','benchmark_qualified','ndx_candidate_admitted','dividend_cash_flows_included','entry_fee_applied','missing_slots_dropped','pooling_only_complete_windows_allowed')

def require(ok,msg):
    if not ok:raise ValueError(msg)
def encoded(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(x):return hashlib.sha256(encoded(x)).hexdigest()
def exact(a,b,msg):require(encoded(a)==encoded(b),msg)
def ref(r):require(type(r) is dict and {'path','sha256'}<=set(r) and type(r['path']) is str and r['path'] and type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Reference')


def inspect_original_eight_scoring_inputs(*,saved_inputs,original_control,control_reference,channel_bindings):
    d=saved_inputs;ref(control_reference);ss=original_control['securities']
    require(type(ss) is list and len(ss)==8 and [s['ticker'] for s in ss]==ORDER and len({s['security_id'] for s in ss})==len({s['issuer_id'] for s in ss})==8,'Original eight identity')
    exact(original_control['complete_original_definition']['securities'],ss,'Definition weights');exact(original_control['complete_original_manifest']['definition'],original_control['complete_original_definition'],'Full manifest');require(original_control['new_execution_contract_frozen'] is False,'No new execution policy')
    require(type(channel_bindings) is list and len(channel_bindings)==8,'Eight bindings')
    sources={control_reference['path']:control_reference['sha256']};weights=[];channels=[]
    for i,(s,b) in enumerate(zip(ss,channel_bindings)):
        exact(s,b['coordinate'],'Full coordinate')
        for k in ('channel_reference','independent_readback_reference'):
            r=b[k];ref(r);require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Source conflict');sources[r['path']]=r['sha256']
        ch=b['channel'];require(ch['ticker']==s['ticker'] and ch['schema']==('ORIGINAL_EIGHT_TSM_SCORING_HISTORY_CHANNEL_V1' if i==4 else 'MULTIDECISION_SCORING_HISTORY_CHANNEL_V1'),'Channel role')
        require(ch['content_sha256']==digest({k:v for k,v in ch.items() if k!='content_sha256'}),'Saved channel checksum')
        require(all(ch[k] is False for k in ('fit_performed','score_computed','point_in_time_verified','source_bytes_authenticated','missing_or_blocked_slots_dropped','unequal_window_pooling_allowed')),'Source authority')
        if i==4:
            require(ch['role']=='CONTROL_ORIGINAL_EIGHT_NOT_NDX_CANDIDATE' and ch['ndx_candidate_admitted'] is False and s['security_id']=='security:incumbent_overlay:TSM' and s['issuer_id']=='issuer:0001046179','TSM only control');exact(ch['original_control_contract']['securities'],ss,'TSM targets')
        w=s['target_weight'];require(type(w) in (str,float,int),'Nonboolean weight');w=float(w);require(math.isfinite(w) and w>=0,'Finite weight');weights.append(w)
        require(len(ch['decisions'])==6 and [x['cutoff'] for x in ch['decisions']]==CUTOFFS,'Six decisions');channels.append(ch)
    total=sum(weights);require(math.isfinite(total) and total>0,'Positive weight sum');normalized=[w/total for w in weights]
    cal=channels[0]['calendar'];require(type(cal) is list and cal==sorted(set(cal)) and all(type(x) is str and date.fromisoformat(x).isoformat()==x and date.fromisoformat(x).weekday()<5 for x in cal),'Canonical calendar')
    for ch in channels:exact(ch['calendar'],cal,'Shared calendar');require(len(ch['return_rows'])==len(cal)-1,'All return slots')
    decisions=[]
    for di,cutoff in enumerate(CUTOFFS):
        p=channels[0]['decisions'][di];dates=p['required_price_dates'];start=p['price_index_start'];require(type(start) is int and start>=0 and len(dates)==505 and dates==cal[start:start+505] and dates[-1]==cutoff,'505 original location')
        for ch in channels:exact(ch['decisions'][di]['required_price_dates'],dates,'Every channel full dates')
        rows=[];bad=[]
        for j in range(504):
            missing=[];products=[]
            for i,ch in enumerate(channels):
                r=ch['return_rows'][start+j];require(r['previous_session']==dates[j] and r['session']==dates[j+1],'Adjacent endpoints');f=r['split_only_return_float'];e=r['split_only_return_exact']
                if f is None:require(e is None,'Null exact pair');missing.append(ss[i]['security_id']);products.append(0.)
                else:require(type(f) is float and math.isfinite(f) and f>-1 and type(e) is str and float(Fraction(e))==f,'Exact saved float');products.append(f*normalized[i])
            if missing:bad.append(j)
            value=0.0
            for product in products:value=value+product
            if missing:value=None
            rows.append(dict(previous_session=dates[j],session=dates[j+1],missing_security_ids=missing,return_float=value))
        windows=[]
        for w in range(13):
            a=w*21;b=[j for j in bad if a<=j<a+252]
            windows.append(dict(window_index=w,training_return_start=a,training_return_stop=a+126,evaluation_return_start=a+126,evaluation_return_stop=a+252,training_freeze_close=dates[a+126],evaluation_first_return_end=dates[a+127],evaluation_last_return_end=dates[a+252],blocked_return_indexes=b,status='BLOCKED_WINDOW' if b else 'CONDITIONAL_NUMERIC_WINDOW'))
        decisions.append(dict(cutoff=cutoff,price_dates=dates,return_rows=rows,windows=windows,status='BLOCKED_FULL13_SCORING_SUPPLY' if bad else 'CONDITIONAL_ALL13_NUMERIC_SUPPLY'))
    expected=dict(schema='ORIGINAL_EIGHT_FIXED_DAILY_WEIGHT_SCORING_INPUTS_V1',role='CONTROL_ORIGINAL_EIGHT_NOT_NDX_CANDIDATE',original_control_preserved=original_control,control_reference=control_reference,channel_binding_evidence=[{k:v for k,v in b.items() if k!='channel'} for b in channel_bindings],declared_source_hashes=sources,normalized_scoring_weights=dict(zip(ORDER,normalized)),original_float_weight_sum=total,weight_normalization_semantics='ORIGINAL_SCORER_FLOAT_CONVERSION_PYTHON_SUM_AND_DIVISION',return_semantics='FIXED_DAILY_WEIGHTED_SAVED_SPLIT_NEUTRAL_RETURNS_PANDAS_MUL_SUM_NOT_FIXED_SHARE_BUY_HOLD',pandas_version=version('pandas'),missing_rows_never_used_as_skipna_returns=True,decisions=decisions,decision_count=6,window_count=78,**dict.fromkeys(FALSE,False))
    expected['content_sha256']=digest(expected);exact(d,expected,'Independent complete projection without tolerance')
    return dict(schema='ORIGINAL_EIGHT_SCORING_ARITHMETIC_INSPECTION_V1',status='PASS',decision_count=6,return_slot_count=3024,window_count=78,arithmetic='ORDERED_BINARY64_ADDITIONS_OF_EIGHT_INDEPENDENT_PRODUCTS_NO_TOLERANCE',numpy_version=np.__version__,pandas_version=version('pandas'),source_bytes_authenticated=False,raw_reconstructed=False,score_computed=False,fit_performed=False,point_in_time_verified=False)
