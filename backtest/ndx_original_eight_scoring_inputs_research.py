"""Original-eight fixed daily-weight scoring input projection; no raw reconstruction."""
from copy import deepcopy
import hashlib,json,math
from datetime import date
from fractions import Fraction
import pandas as pd

ORDER=['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG']
CUTOFFS=['2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31']
FLAGS=('source_bytes_authenticated','historical_identity_verified','historical_risk_verified','point_in_time_verified','execution_authorized','promotion_allowed','fit_performed','score_computed','raw_reconstructed','account_simulated','benchmark_qualified','ndx_candidate_admitted','dividend_cash_flows_included','entry_fee_applied','missing_slots_dropped','pooling_only_complete_windows_allowed')

def require(ok,msg):
    if not ok:raise ValueError(msg)

def encoded(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(x):return hashlib.sha256(encoded(x)).hexdigest()
def exact(a,b,msg):require(encoded(a)==encoded(b),msg)
def ref(r):require(type(r) is dict and {'path','sha256'}<=set(r) and type(r['path']) is str and r['path'] and type(r['sha256']) is str and len(r['sha256'])==64 and all(c in '0123456789abcdef' for c in r['sha256']),'Source reference')


def prepare_original_eight_scoring_inputs(*,original_control,control_reference,channel_bindings):
    ref(control_reference);ss=original_control['securities']
    require(type(ss) is list and len(ss)==8 and [s['ticker'] for s in ss]==ORDER,'Original eight order')
    require(len({s['security_id'] for s in ss})==len({s['issuer_id'] for s in ss})==8,'Distinct original control coordinates')
    exact(original_control['complete_original_definition']['securities'],ss,'Original definition weights')
    exact(original_control['complete_original_manifest']['definition'],original_control['complete_original_definition'],'Original manifest')
    require(original_control['new_execution_contract_frozen'] is False,'Not new execution policy')
    require(type(channel_bindings) is list and len(channel_bindings)==8,'Eight explicit bindings')
    sources={control_reference['path']:control_reference['sha256']};weights={};channels=[]
    for i,(s,b) in enumerate(zip(ss,channel_bindings)):
        exact(b['coordinate'],s,'Full original coordinate/weight binding')
        for k in ('channel_reference','independent_readback_reference'):
            r=b[k];ref(r);require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Source conflict');sources[r['path']]=r['sha256']
        ch=b['channel'];require(ch['ticker']==s['ticker'],'Ticker identity')
        require(ch['schema']==('ORIGINAL_EIGHT_TSM_SCORING_HISTORY_CHANNEL_V1' if i==4 else 'MULTIDECISION_SCORING_HISTORY_CHANNEL_V1'),'Control/candidate channel schema')
        if i==4:
            require(ch['role']=='CONTROL_ORIGINAL_EIGHT_NOT_NDX_CANDIDATE' and ch['ndx_candidate_admitted'] is False and s['security_id']=='security:incumbent_overlay:TSM' and s['issuer_id']=='issuer:0001046179','TSM control role')
            exact(ch['original_control_contract']['securities'],ss,'TSM original eight target')
        require(ch['content_sha256']==digest({k:v for k,v in ch.items() if k!='content_sha256'}),'Channel content checksum')
        require(all(ch[k] is False for k in ('fit_performed','score_computed','point_in_time_verified','source_bytes_authenticated','missing_or_blocked_slots_dropped','unequal_window_pooling_allowed')),'Conditional channel only')
        v=s['target_weight'];require(type(v) in (str,int,float),'Original nonboolean weight');v=float(v);require(math.isfinite(v) and v>=0,'Finite nonnegative original weight');weights[s['ticker']]=v
        require(len(ch['decisions'])==6 and [d['cutoff'] for d in ch['decisions']]==CUTOFFS,'All six cutoff slots')
        channels.append(ch)
    total=sum(weights.values());require(math.isfinite(total) and total>0,'Positive original total')
    normalized={t:w/total for t,w in weights.items()}
    base=channels[0]
    cal=base['calendar'];require(type(cal) is list and cal==sorted(set(cal)) and all(type(d) is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5 for d in cal),'Canonical unique weekday calendar')
    for ch in channels[1:]:exact(ch['calendar'],base['calendar'],'Common full source calendar')
    decisions=[]
    for di,cutoff in enumerate(CUTOFFS):
        parent=base['decisions'][di];dates=parent['required_price_dates'];require(len(dates)==505 and dates==sorted(set(dates)) and dates[-1]==cutoff,'Exact505 cutoff')
        start=parent['price_index_start'];require(type(start) is int and start>=0 and base['calendar'][start:start+505]==dates,'Calendar location')
        for ch in channels:
            exact(ch['decisions'][di]['required_price_dates'],dates,'Same505 for every control')
            require(len(ch['return_rows'])==len(ch['calendar'])-1,'Full source return slots')
        series=[];blocked=[];rows=[]
        for j in range(504):
            vals=[];miss=[]
            for s,ch in zip(ss,channels):
                r=ch['return_rows'][start+j];require(r['previous_session']==dates[j] and r['session']==dates[j+1],'Adjacent source return slot')
                f=r['split_only_return_float']
                if f is None:require(r['split_only_return_exact'] is None,'Missing exact/float pair');miss.append(s['security_id'])
                else:
                    require(type(f) is float and math.isfinite(f) and f>-1,'Saved return float')
                    e=r['split_only_return_exact'];require(type(e) is str and float(Fraction(e))==f,'Saved exact/float consistency')
                vals.append(f)
            rows.append(dict(previous_session=dates[j],session=dates[j+1],missing_security_ids=miss))
            series.append(vals)
            if miss:blocked.append(j)
        # Identical fixed-weight daily reduction used by the original scorer.
        frame=pd.DataFrame(series,columns=ORDER,dtype='float64')
        values=frame.mul(pd.Series(normalized),axis=1).sum(axis=1)
        for j,row in enumerate(rows):row['return_float']=None if j in blocked else float(values.iloc[j])
        windows=[]
        for w in range(13):
            a=w*21;bad=[j for j in blocked if a<=j<a+252]
            windows.append(dict(window_index=w,training_return_start=a,training_return_stop=a+126,evaluation_return_start=a+126,evaluation_return_stop=a+252,training_freeze_close=dates[a+126],evaluation_first_return_end=dates[a+127],evaluation_last_return_end=dates[a+252],blocked_return_indexes=bad,status='BLOCKED_WINDOW' if bad else 'CONDITIONAL_NUMERIC_WINDOW'))
        decisions.append(dict(cutoff=cutoff,price_dates=deepcopy(dates),return_rows=rows,windows=windows,status='BLOCKED_FULL13_SCORING_SUPPLY' if blocked else 'CONDITIONAL_ALL13_NUMERIC_SUPPLY'))
    out=dict(schema='ORIGINAL_EIGHT_FIXED_DAILY_WEIGHT_SCORING_INPUTS_V1',role='CONTROL_ORIGINAL_EIGHT_NOT_NDX_CANDIDATE',original_control_preserved=deepcopy(original_control),control_reference=deepcopy(control_reference),channel_binding_evidence=[{k:deepcopy(v) for k,v in b.items() if k!='channel'} for b in channel_bindings],declared_source_hashes=sources,normalized_scoring_weights=normalized,original_float_weight_sum=total,weight_normalization_semantics='ORIGINAL_SCORER_FLOAT_CONVERSION_PYTHON_SUM_AND_DIVISION',return_semantics='FIXED_DAILY_WEIGHTED_SAVED_SPLIT_NEUTRAL_RETURNS_PANDAS_MUL_SUM_NOT_FIXED_SHARE_BUY_HOLD',pandas_version=pd.__version__,missing_rows_never_used_as_skipna_returns=True,decisions=decisions,decision_count=6,window_count=78,**dict.fromkeys(FLAGS,False))
    out['content_sha256']=digest(out);return out
