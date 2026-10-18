"""Independent Fraction readback of the saved fixed-share diagnostic."""
from decimal import Context,Decimal,localcontext
from fractions import Fraction
import hashlib,json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve()
SELF_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASE=ROOT/'data/cache/research/dated_continuous_weight_diagnostic_20261003_v1'
REFS={
 'diagnostic':dict(path=str(BASE/'diagnostic.json'),sha256='bb81bc97c9bb5564afeab9eed4a1421e40fe5274ae29807ce9994bd7b70b8c7f'),
 'publication':dict(path=str(BASE/'publication.json'),sha256='ad10068b3b2efa98ce13cdef62c52d096c085680343078a8c429daf5225144d8'),
 'inputs':dict(path=str(ROOT/'data/cache/research/dated_account_inputs_20261003_v1/89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3/inputs.json'),sha256='ac0201e24925dff189d25e4fb5f0a8c741d567c31060f2aa48e3e2232fd90409'),
 'input_readback':dict(path=str(ROOT/'data/cache/research/dated_account_inputs_20261003_v1/89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3/independent_readback.json'),sha256='396b45c1eec5a3fa0f2441744d409c0642eb21d2f6719da33725360707e114a3'),
}

def require(ok,message):
    if not ok:raise ValueError(message)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encode(a)==encode(b),message)
def sha(b):return hashlib.sha256(b).hexdigest()
def rational(v):
    require(type(v) is dict and set(v)=={'numerator','denominator'} and all(type(x) is str for x in v.values()),'Exact ratio object')
    n=Fraction(int(v['numerator']),int(v['denominator']))
    exact(v,dict(numerator=str(n.numerator),denominator=str(n.denominator)),'Canonical ratio')
    return n
def check(value,expected,label):require(rational(value)==expected,label)
def read(r,sources):
    blob=Path(r['path']).read_bytes();require(sha(blob)==r['sha256'],'External bytes')
    require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Hash conflict');sources[r['path']]=r['sha256'];return json.loads(blob)

def inspect(track,source,calendar):
    exact(track['calendar'],calendar,'Full calendar');require(type(track['interval_count']) is int and track['interval_count']==126,'126 intervals')
    order=source['original_security_order'];targets=source['schedule'][0]['targets'];weights={s:Fraction(str(targets[s]['target_weight'])) for s in order}
    expected_positions=[dict(security_id=s,ticker=source['original_ticker_by_security'][s],issuer_id=targets[s]['issuer_id'],target_weight=targets[s]['target_weight']) for s in order]
    exact(track['positions_preserved'],expected_positions,'Original complete weights')
    check(track['weight_sum_exact'],sum(weights.values()),'Original weight total')
    events={(e['security_id'],e['session']):Fraction(e['new_shares'],e['old_shares']) for e in source['corporate_actions']}
    require(len(events)==len(source['corporate_actions']),'Unique explicit events')
    require([p['session'] for p in track['path']]==calendar,'Full127 path')
    qty={s:Fraction() for s in order};values=[]
    for i,(session,point) in enumerate(zip(calendar,track['path'])):
        require([r['security_id'] for r in point['security_rows']]==order,'All SID contribution rows')
        total=Fraction()
        for sid,row in zip(order,point['security_rows']):
            quote=source['exact_quote_conversion_evidence'][sid][i]
            require(quote['session']==session,'Quote date')
            ratio=events.get((sid,session),Fraction(1))
            if i:qty[sid]*=ratio
            if i==1:qty[sid]=weights[sid]/Fraction(quote['open']['exact'])
            contribution=qty[sid]*Fraction(quote['close']['exact']) if i else Fraction()
            check(row['fractional_quantity'],qty[sid],'Held fractional quantity')
            check(row['contribution_before_cost'],contribution,'Before one cost factor')
            check(row['contribution_after_cost'],contribution*Fraction(999,1000),'After one cost factor')
            if i:
                require(row['entry_purchase'] is (i==1),'Only one entry')
                check(row['nominal_close_exact'],Fraction(quote['close']['exact']),'Exact nominal mark')
                check(row['split_ratio_before_purchase_or_mark'],ratio,'Split before entry or mark')
            total+=contribution*Fraction(999,1000)
        value=Fraction(1) if i==0 else total
        require(value>0,'Positive normalized path');check(point['normalized_value'],value,'Every independent NAV')
        with localcontext(Context(prec=80)):display=str(Decimal(value.numerator)/Decimal(value.denominator))
        require(point['normalized_value_display']==display,'Display precision')
        values.append(value)
    cumulative=values[-1]-1;annual=values[-1]**2-1
    dd=max(Fraction(0),max(1-values[j]/values[i] for i in range(127) for j in range(i,127)))
    peak=values[0];pi=0;largest=Fraction();pair=(0,0)
    for j,value in enumerate(values):
        if value>peak:peak=value;pi=j
        decline=1-value/peak
        if decline>largest:largest=decline;pair=(pi,j)
    require(largest==dd,'All-pairs drawdown oracle')
    for key,value in [('cumulative_return_exact',cumulative),('annualized_return_exact',annual),('max_drawdown_exact',dd)]:check(track[key],value,key)
    require(track['drawdown_peak_index']==pair[0] and track['drawdown_trough_index']==pair[1] and track['drawdown_peak_session']==calendar[pair[0]] and track['drawdown_trough_session']==calendar[pair[1]],'First strict peak/trough')
    for key in ('weights_normalized','weights_refitted','daily_rebalancing_performed','point_in_time_verified','promotion_allowed','future_independent_oos','untouched_holdout','accounting_conservation_verified','formal_cohort_verified'):require(track[key] is False,'Diagnostic only')
    return dict(point_count=127,security_point_count=127*len(order),cumulative_return_percent=float(cumulative*100),annualized_return_percent=float(annual*100),maximum_drawdown_percent=float(dd*100),drawdown_peak_session=calendar[pair[0]],drawdown_trough_session=calendar[pair[1]])

def run():
    output=ROOT/'DYNAMIC_DATED_CONTINUOUS_INDEPENDENT_READBACK_20261003.json';require(not output.exists(),'Independent result already exists')
    sources={str(SOURCE):SELF_SHA};docs={role:read(r,sources) for role,r in REFS.items()}
    d=docs['diagnostic'];p=docs['publication'];inp=docs['inputs']['inputs'];audit=docs['input_readback']
    require(d['schema']=='SOURCE_BOUND_DATED_CONTINUOUS_WEIGHT_DIAGNOSTIC_V1' and p['schema']=='DATED_CONTINUOUS_DIAGNOSTIC_PUBLICATION_V1' and p['status']=='PUBLISHED_CONDITIONAL_FRACTIONAL_DIAGNOSTIC_NOT_ACCOUNT','Diagnostic publication')
    exact(p['diagnostic_reference'],REFS['diagnostic'],'Publication payload');exact(p['source_hashes'],d['source_hashes'],'Sources')
    exact(d['input_references']['inputs'],REFS['inputs'],'Input anchor');exact(d['input_references']['readback'],REFS['input_readback'],'Input audit anchor')
    require(audit['schema']=='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Audited inputs')
    exact(audit['inputs_reference'],REFS['inputs'],'Audit payload')
    for path,h in d['source_hashes'].items():require(path not in sources or sources[path]==h,'Source conflict');sources[path]=h
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Direct source drift')
    counts={role:inspect(d['tracks'][role],inp[role],inp['calendar']) for role in ('candidate','incumbent')}
    value=dict(schema='DATED_CONTINUOUS_INDEPENDENT_READBACK_V1',status='PASS',diagnostic_reference=REFS['diagnostic'],publication_reference=REFS['publication'],reader_sha256=SELF_SHA,tracks=counts,source_hashes=sources,producer_called=False,account_executed=False,fit_performed=False,point_in_time_verified=False,promotion_allowed=False,future_independent_oos=False)
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Final source drift')
    blob=encode(value)
    with output.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    require(output.read_bytes()==blob,'Durable audit');return dict(path=str(output),sha256=sha(blob),tracks=counts)

if __name__=='__main__':print(json.dumps(run()))
