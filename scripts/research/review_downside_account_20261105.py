"""Independent max10 downside arithmetic and saved-account reviewer; no search."""
import argparse
import gzip
import inspect
import json
import math
import sys
from copy import deepcopy
from datetime import datetime
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backtest import historical_dividend_identity_independent_review_v1 as finance
from backtest import capped_frontier_independent_review as frontier
from scripts.research.review_qqq_risk_budget_20261105 import audit_zero_identity_events

ENCODING = 'RESEARCH_EXACT_FRACTION_HEX_JSON_V1'
TAG = '__research_exact_fraction_hex_v1__'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def unpack(document):
    require(set(document) == {'encoding', 'payload'} and document['encoding'] == ENCODING, 'CODEC_VERSION')
    def decode(item):
        if isinstance(item, list): return [decode(v) for v in item]
        if isinstance(item, dict):
            if TAG in item:
                require(set(item) == {TAG} and set(item[TAG]) == {'numerator', 'denominator'}, 'CODEC_FRACTION_SCHEMA')
                pair = [item[TAG][k] for k in ('numerator', 'denominator')]
                require(all(type(v) is str and hex(int(v,16)) == v for v in pair), 'CODEC_CANONICAL_HEX')
                n, d = (int(v,16) for v in pair)
                require(d > 0, 'CODEC_DENOMINATOR')
                return F(n,d)
            return {k:decode(v) for k,v in item.items()}
        return item
    return decode(document['payload'])


def read(path, encoded=False):
    doc = json.loads(Path(path).read_bytes())
    return unpack(doc) if encoded else doc


def canonical(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def evidence_hash(value):
    def encode(item):
        if isinstance(item,F): return {TAG:dict(numerator=hex(item.numerator),denominator=hex(item.denominator))}
        if isinstance(item,dict):
            require(TAG not in item,'RESERVED_TAG')
            return {k:encode(v) for k,v in item.items()}
        if isinstance(item,(list,tuple)): return [encode(v) for v in item]
        return item
    # Evidence hashes use the versioned envelope and default JSON ASCII policy.
    envelope=dict(encoding=ENCODING,payload=encode(value))
    return sha256(json.dumps(envelope,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def product_hash(value):
    return sha256(f'{value.numerator:x}/{value.denominator:x}'.encode()).hexdigest()


def score(quantities,args, enforce_cap=True):
    require(all(s in args['prices'] and type(q) is int and q>0 for s,q in quantities.items()),'POSITIVE_INTEGER_TARGETS')
    capital=F(args['entered_cash']);fee=F(args['fee_bps'])/10000
    require(capital>0 and 0<=fee<1,'CAPITAL_COST')
    require(len({args['metadata'][s]['issuer_id'] for s in quantities})==len(quantities),'ISSUER_UNIQUENESS')
    if enforce_cap: require(all(q*F(args['prices'][s])*2<=capital for s,q in quantities.items()),'CAP50')
    notional=sum((q*F(args['prices'][s]) for s,q in quantities.items()),F(0))
    cash=capital-notional*(1+fee)
    require(cash>=0 and (not quantities or cash>=F(args['minimum_cash_buffer'])),'CASH_BUFFER')
    growth=[(cash+sum((q*F(args['prices'][s])*F(row[s]) for s,q in quantities.items()),F(0)))/capital for row in args['training_scenarios']]
    require(all(v>0 for v in growth),'POSITIVE_SCENARIO_WEALTH')
    return dict(product=math.prod(growth),notional=notional,residual_cash=cash)


def risk(quantities,args,returns,reference):
    dates=list(reference)
    require(len(dates)==252 and dates==sorted(set(dates)) and dates[-1]==args['decision_date'],'RISK_DATES')
    weights={s:q*F(args['prices'][s])/F(args['entered_cash']) for s,q in quantities.items() if q}
    values=[sum((w*F(returns[s][d]) for s,w in weights.items()),F(0)) for d in dates]
    moment=lambda xs:sum((v*v for v in xs if v<0),F(0))/len(xs)
    value,qqq=moment(values),moment([F(reference[d]) for d in dates])
    return value<=qqq,value,qqq


def review_selection(selected,sidecar,returns,reference,pins):
    raw=selected['raw_selection'];args=frontier._binding(raw)
    require(selected['method']=='SAME_CALL_OBSERVED_DOWNSIDE_QQQ_V1','SELECTION_METHOD')
    require(set(returns)==set(args['prices']) and len(args['training_scenarios'])==12,'RETURN_DOMAIN')
    dates=list(reference)
    require(args['scenario_dates']==dates[20::21],'SCENARIO_DATES')
    for sid,rows in returns.items():
        require(list(rows)==dates and all(F(v)>-1 for v in rows.values()),'COMMON_POSITIVE_GROSS')
        for i,row in enumerate(args['training_scenarios']):
            require(math.prod(1+F(rows[d]) for d in dates[i*21:(i+1)*21])==F(row[sid]),'DAILY_12_SCENARIO_COORDINATES')
    require(all(F(v)>-1 for v in reference.values()),'QQQ_POSITIVE_GROSS')
    require(evidence_hash({k:v for k,v in sidecar.items() if k!='integrity_sha256'})==sidecar['integrity_sha256']==raw['downside_sidecar_sha256'],'SIDECAR_DIGEST')
    expected_binding=dict(capital_decision_id=raw['decision_id'],capital_binding_sha256=evidence_hash(raw['binding']),
        search_arguments_sha256=evidence_hash(args),capital_source_hashes=raw['binding']['source_hashes'],
        research_source_hashes=pins,stock_return_coordinates_sha256=evidence_hash(returns),qqq_coordinates_sha256=evidence_hash(reference))
    require(sidecar['evidence_binding']==expected_binding,'SIDECAR_DYNAMIC_BINDING')
    require(sidecar['complete'] is True and sidecar['max_holdings']==10,'COMPLETE_MAX10')
    counts=sidecar['coverage'];phases=sidecar['phase_counts'];search=raw['search_result']
    require(all(type(v) is int and v>=0 for v in counts.values()),'COUNT_DOMAIN')
    require(counts['risk_evaluated']==counts['capped_unique']-counts['over_holdings_limit']<=10000,'COVERAGE_COUNTS')
    require(counts['raw_unique_observed']>=counts['capped_unique']>=counts['over_holdings_limit'],'COVERAGE_ORDER')
    require(phases['base']==search['objective_evaluations'] and phases['comparison']==sum(search['continuous_comparison']['exact_evaluations'][k] for k in ('saved_unique','new_unique')),'PHASE_COUNTS')
    # Reconstruct original V27 rerank target independently from saved frontier.
    cap=lambda q:{s:min(n,int(F(args['entered_cash'])/(2*F(args['prices'][s])))) for s,n in q.items()}
    base=cap(raw['target_quantities']);base_score=score({s:q for s,q in base.items() if q},args)
    baskets={tuple(sorted((s,q) for s,q in cap(row['quantities']).items() if q)) for row in search['best_by_k'].values()}
    improved=[q for q in baskets if score(dict(q),args)['product']>base_score['product']]
    incumbent=dict(max(improved,key=lambda q:(score(dict(q),args)['product'],-score(dict(q),args)['notional'],q))) if improved else base
    original=deepcopy(selected)
    original.update(method='SAME_CALL_SAVED_FRONTIER_CAP50_STRICT_RERANK_V1',target_quantities=incumbent,rerank_audit=selected['original_rerank_audit'])
    bind=dict(schema=original['method'],original_decision_id=raw['decision_id'],original_raw_selection_sha256=canonical(raw),
        target_quantities=incumbent,base_capped_target_quantities=base,monthly_cap_fraction='1/2',rerank_audit=original['rerank_audit'])
    original.update(rerank_binding=bind,rerank_decision_id=canonical(bind))
    proof=frontier.review_selection(original,rerank_enabled=True)
    incumbent_positive={s:q for s,q in incumbent.items() if q}
    incumbent_score=score(incumbent_positive,args)
    inc_pass,inc_risk,qqq_risk=risk(incumbent,args,returns,reference)
    inc_pass=inc_pass and len(incumbent_positive)<=10
    records=[sidecar['cash'],*sidecar['eligible_best_by_k'].values()]
    require(sidecar['cash']['target_quantities']=={} and sidecar['cash_fallback_seeded'] is True,'CASH_FALLBACK')
    for key,record in sidecar['eligible_best_by_k'].items():
        require(str(record['actual_k'])==key and 1<=int(key)<=10,'CARDINALITY_KEY')
    assessed=[]
    for record in records:
        quantities=record['target_quantities'];s=score(quantities,args)
        require(len(quantities)==record['actual_k']<=10,'MAX10_ACTUAL')
        require(s['product']==record['exact_product'] and s['notional']==record['notional'] and s['residual_cash']==record['residual_cash'],'SIDECAR_EXACT_SCORE')
        passed,value,_=risk(quantities,args,returns,reference)
        require(passed,'EXACT_DOWNSIDE_GATE')
        low,high=map(F,record['downside_interval']);require(low<=value<=high,'DOWNSIDE_INTERVAL')
        if record['source_phase']=='EXPLICIT_CASH_FALLBACK_NOT_SEARCH_OBSERVATION':
            require(not quantities and record['source_evaluation_index'] is None,'CASH_PROVENANCE')
        else:
            require(record['source_phase'] in ('base','comparison') and type(record['source_evaluation_index']) is int and record['source_evaluation_index']>=0,'OBSERVED_PROVENANCE')
            raw_quantities=dict(record['raw_signature']);score(raw_quantities,args,False)
            require({s:q for s,q in cap(raw_quantities).items() if q}==quantities,'OBSERVED_CAP_MAPPING')
        assessed.append((quantities,s))
    eligible=[(q,s) for q,s in assessed if not inc_pass or s['product']>incumbent_score['product']]
    chosen,chosen_score=max(eligible,key=lambda pair:(pair[1]['product'],-pair[1]['notional'],tuple(sorted(pair[0].items())))) if eligible else (incumbent,incumbent_score)
    require(selected['target_quantities']==chosen,'INDEPENDENT_DOWNSIDE_WINNER')
    audit=selected['downside_audit']
    require(audit==dict(incumbent='ACTUAL_V27_SAVED_FRONTIER_CAP50_RERANK',incumbent_admitted=inc_pass,
        incumbent_product_sha256=product_hash(incumbent_score['product']),selected_product_sha256=product_hash(chosen_score['product']),coverage=counts,
        tie_rule='ADMITTED_ACTUAL_V27_INCUMBENT_RETAINED_UNLESS_STRICT_PRODUCT_IMPROVEMENT',holding_count_limit=10,source_authenticated=False),'DOWNSIDE_AUDIT')
    bind=dict(schema=selected['method'],original_rerank_decision_id=original['rerank_decision_id'],target_quantities=chosen,downside_audit=audit)
    require(selected['rerank_binding']==bind and selected['rerank_decision_id']==canonical(bind),'DOWNSIDE_SELECTION_BINDING')
    proof['target_quantities']=chosen
    return proof,dict(incumbent_admitted=inc_pass,incumbent_downside=str(inc_risk),qqq_downside=str(qqq_risk),
        retained_records_checked=len(records),target=chosen,full_observed_winner_dominance_proven=False)


def run(output):
    sys.set_int_max_str_digits(100000)
    directory=ROOT/output;contract=read(directory/'contract.json',True)
    require(contract['candidate']=='SAME_CALL_OBSERVED_DOWNSIDE_QQQ_V1' and contract['serialization_policy']==ENCODING and contract['max_holdings']==10,'CONTRACT')
    require((contract['initial_cash'],contract['fee_bps'],contract['slippage_bps'])==('20000','0','5')
            and contract['seconds']==10800 and contract['monthly_seconds']==600,'FROZEN_COST_BUDGET')
    for name,h in contract['source_hashes'].items():require(sha256((ROOT/name).read_bytes()).hexdigest()==h,'SOURCE_CHANGED:'+name)
    book=read(directory/'book.json',True);require(book['status']=='COMPLETE','COMPLETE_REQUIRED')
    late=contract['window']=='2024_2026';base='old_continuous_baseline_20261026_v9' if late else 'recent_continuous_baseline_20261026_v7'
    document=read(ROOT/'tmp'/base/'execution_inputs.json')
    document['dividend_events'].extend(read(ROOT/'tmp/equal_four_20261105/source_review/admitted_supplement.json')['dividend_events'][contract['window']])
    bounded=read(directory/'bounded_execution_evidence.json',True)
    source=read(ROOT/'tmp/risk_budget_64d_inventory_20261105/bounded_supplement.json')
    metadata={s:m for p in document['assembled']['monthly_inputs'] for s,m in p['search_arguments']['metadata'].items()}
    for event in bounded['events']:
        matches=[e for e in source['events'] if e['ticker']==metadata[event['security_id']]['ticker'] and e['ex_date']==event['ex_date']]
        require(len(matches)==1,'BOUNDED_DIVIDEND_SOURCE')
        expected=matches[0]
        require(F(event['amount_per_share'])==F(expected['amount_per_share']) and event['payment_date']==expected['payment_date'] and event['currency']=='USD' and F(event['withholding_rate'])==0,'BOUNDED_DIVIDEND_UNITS')
        require(any(r.get('security_id')==event['security_id'] and r.get('ex_date')==event['ex_date'] and r.get('status')=='REVIEWED_ORDINARY_CASH_DIVIDEND' for r in bounded['review_rows']),'DIVIDEND_GATE_AND_BOOK')
    document['dividend_events'].extend(bounded['events'])
    dates=document['assembled']['session_dates'];require(len(dates)-1==(646 if late else 753) and (dates[0],dates[-1])==(contract['start'],contract['end']),'FULL_WINDOW')
    require(contract['maximum_new_searches']==(31 if late else 36),'FROZEN_MONTH_LIMIT')
    # Prove completeness too: an omitted reviewed ordinary dividend is not
    # excused merely because every remaining event has valid metadata.
    for expected in source['events']:
        if not dates[0]<expected['ex_date']<=dates[-1]:continue
        matches=[e for e in document['dividend_events'] if e['ex_date']==expected['ex_date']
                 and metadata[e['security_id']]['ticker']==expected['ticker']]
        require(len(matches)==1,'BOUNDED_DIVIDEND_COMPLETE_UNIQUE')
        event=matches[0]
        require(F(event['amount_per_share'])==F(expected['amount_per_share']) and event['payment_date']==expected['payment_date'],
                'BOUNDED_DIVIDEND_COMPLETE_UNITS')
    training=read(ROOT/('tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json' if late else 'tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json'))
    windows={}
    for outer in training['windows']:
        w=outer.get('window',outer);windows[w.get('decision_cutoff',w.get('decision_date'))]=w
    qprices={}
    for name in ('tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin'):
        raw=(ROOT/name).read_bytes();series=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['chart']['result'][0]
        require(series['meta']['symbol']=='QQQ' and not series.get('events',{}).get('splits'),'QQQ_SOURCE')
        for t,c in zip(series['timestamp'],series['indicators']['quote'][0]['close']):
            if c is None:continue
            d=datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat();value=F(str(c))
            require(d not in qprices or qprices[d]==value,'QQQ_OVERLAP');qprices[d]=value
    checked={}
    def review(selected,*,rerank_enabled):
        day=selected['raw_selection']['decision_date'];w=windows[day];ds=w['training_dates']
        require(len(ds)==253 and ds==sorted(set(ds)) and ds[-1]==day,'TRAINING_WINDOW')
        candidates={c['security_id']:c for c in w['candidates'] if c.get('security_id')};returns={}
        for sid in selected['raw_selection']['binding']['search_arguments']['prices']:
            values=list(map(F,candidates[sid]['training_close']));require(len(values)==253 and all(v>0 for v in values),'TRAINING_PRICES')
            returns[sid]={d:b/a-1 for d,a,b in zip(ds[1:],values,values[1:])}
        reference={b:qprices[b]/qprices[a]-1 for a,b in zip(ds,ds[1:])}
        gate=read(directory/(day+'.exposure.json'),True);require(gate['admitted'] is True,'ACTION_GATE_REJECTED')
        side=read(directory/(day+'.sidecar.json'),True)
        saved=read(directory/(day+'.decision.json'),True);require(saved['selected']==selected,'SAVED_DECISION')
        proof,check=review_selection(selected,side,returns,reference,contract['source_hashes']);checked[day]=check
        return proof
    _,_,zero=audit_zero_identity_events(book,document['assembled'])
    namespace=dict(finance.__dict__);namespace['review_selection']=review
    code=inspect.getsource(finance.review)
    if zero:
        old="            if successor != sid:\n                require(successor not in terminated"
        old2="            if shares.get(sid, 0) or any(o['security_id'] == sid for o in orders):"
        require(code.count(old)==1 and code.count(old2)==1,'IDENTITY_AUDIT_ANCHORS')
        code=code.replace(old,"            if successor != sid and (day, sid) not in proved_zero_identities:\n                require(successor not in terminated").replace(old2,old2[:-1]+' or (day, sid) in proved_zero_identities:')
        namespace['proved_zero_identities']={(p['event']['date'],p['event']['security_id']) for p in zero}
    exec(compile(code,'<independent-downside-account-finance>','exec'),namespace)
    result=namespace['review'](book,document['assembled'],document['ohlc'],initial_cash='20000',dividend_events=document['dividend_events'],verify_selections=True,verify_risk_provider=True,expected_fee_bps='0',expected_slippage_bps='5')
    result['integer_identity_liquidations_checked']-=len(zero);result['zero_exposure_identity_events_checked']=len(zero)
    require(len(checked)==(31 if late else 36),'FULL_MONTHS')
    paths=[Path(__file__),Path(finance.__file__),Path(frontier.__file__),ROOT/'scripts/research/review_qqq_risk_budget_20261105.py',directory/'contract.json',directory/'book.json',directory/'bounded_execution_evidence.json']
    paths += [directory/(d+suffix) for d in checked for suffix in ('.sidecar.json','.decision.json','.exposure.json')]
    report=dict(status='INDEPENDENT_DOWNSIDE_MAX10_FINANCE_PASS',finance=result,months_checked=len(checked),selection_checks=checked,
        zero_exposure_identity_proofs=zero,candidate_apply_called=False,candidate_integer_helper_called=False,economic_replays=0,
        limitations='Retained per-k feasibility/score and reported coverage verified; full observed-candidate dominance cannot be independently proven without all candidate records. Conditional sources, not PIT/OOS or profitability guarantee.',
        source_hashes={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths})
    (directory/'independent_review.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(status=report['status'],finance=result,months_checked=len(checked))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)
