"""31 saved decisions: exact held-basket score and risk, no search or replay."""
import json,gzip,time
from pathlib import Path
from hashlib import sha256
from fractions import Fraction as F
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
from math import prod
from backtest.research_exact_fraction_json import loads,dumps
from docs.candidates.downside_account_selection_20261105 import exact_hash
from scripts.audit_capped_training_frontier import evaluate,capped
from scripts.research.preflight_downside_frontier_20261105 import bounds,classify
from scripts.run_old_continuous_probe_v1 import validate_selection_binding

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'tmp/downside_max10_20261105_late_v9'


def run():
    started=time.monotonic();output=ROOT/'tmp/retained_holdings_static_20261105_v2';output.mkdir(exist_ok=False)
    def read(path):
        raw=Path(path).read_bytes();plain=json.loads(raw)
        return loads(raw) if plain.get("encoding")=="RESEARCH_EXACT_FRACTION_HEX_JSON_V1" else plain
    contract=read(BASE/'contract.json');pins=contract['source_hashes'];verified={}
    def check(name):
        if sha256((ROOT/name).read_bytes()).hexdigest()!=pins[name]:raise ValueError('FROZEN_SOURCE_CHANGED:'+name)
        verified[name]=pins[name]
    # All frozen dependencies checked once; newly written local result files are
    # additionally bound below, not misrepresented as prior trusted input hashes.
    for name in pins:check(name)
    book=read(BASE/'book.json');assert book['status']=='COMPLETE'
    parent_states={r['decision_date']:r for r in book['selection_account_states']}
    train_name='tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json'
    training=read(ROOT/train_name);windows={}
    for outer in training['windows']:
        item=outer.get('window',outer);windows[item.get('decision_cutoff',item.get('decision_date'))]=item
    qprices={}
    for name in ['tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin']:
        raw=(ROOT/name).read_bytes();body=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['chart']['result'][0]
        for stamp,value in zip(body['timestamp'],body['indicators']['quote'][0]['close']):
            if value is None:continue
            day=datetime.fromtimestamp(stamp,ZoneInfo('America/New_York')).date().isoformat();value=F(str(value))
            if day in qprices:assert qprices[day]==value
            qprices[day]=value
    records=[];local_hashes={}
    paths=sorted(BASE.glob('*.selection.json'));assert len(paths)==31
    for path in paths:
        selection=read(path);day=selection['arguments']['decision_date'];args=selection['arguments'];raw=selection['raw_selection']
        validate_selection_binding(raw,args)
        assert args==parent_states[day]
        decision_path=BASE/(day+'.decision.json');decision=read(decision_path)
        assert decision['arguments']==args
        for p in (path,decision_path):local_hashes[p.relative_to(ROOT).as_posix()]=sha256(p.read_bytes()).hexdigest()
        score_args=raw['binding']['search_arguments'];equity=F(score_args['entered_cash'])
        actual=args['account_state'];held={s:q for s,q in actual['shares'].items() if q}
        chosen={s:q for s,q in decision['selected']['target_quantities'].items() if q}
        quotes={q['security_id']:q for q in args['valuation_quotes']}
        assert F(actual['cash'])+sum((q*F(quotes[s]['price']) for s,q in held.items()),F(0))==equity
        held_weight={s:str(q*F(quotes[s]['price'])/equity) for s,q in held.items()}
        new_weight={s:str(q*F(score_args['prices'][s])/equity) for s,q in chosen.items()}
        failures=[]
        if not held:failures.append('NO_POSITIVE_HOLDINGS')
        if any(type(q)is not int or q<=0 for q in held.values()):failures.append('INTEGER_SHARES')
        if not set(held)<=set(score_args['prices']):failures.append('OUTSIDE_CURRENT_TRAINING_DOMAIN')
        if len(held)>10:failures.append('OVER_TEN_HOLDINGS')
        holding_score=None;risk_interval=None;ratio=None;relation=None;coordinate_checked=False
        if not failures:
            if len({score_args['metadata'][s]['issuer_id'] for s in held})!=len(held):failures.append('DUPLICATE_ISSUER')
            if capped(held,score_args)!=held:failures.append('CAP50_WOULD_CHANGE_HOLDINGS')
            try:
                holding_score=evaluate(held,score_args)
                if holding_score['residual_cash']!=F(actual['cash']):failures.append('RETAIN_CASH_MISMATCH')
            except ValueError as error:failures.append('SCORE_ADMISSION:'+str(error))
        if not failures:
            item=windows[day];dates=item['training_dates'];assert len(dates)==253 and dates[-1]==day
            candidates={c['security_id']:c for c in item['candidates'] if c.get('security_id')}
            series={}
            for sid in held:
                values=list(map(F,candidates[sid]['training_close']));assert len(values)==253 and all(x>0 for x in values)
                returns=[b/a-1 for a,b in zip(values,values[1:])]
                assert all(prod(1+x for x in returns[i*21:(i+1)*21])==F(score_args['training_scenarios'][i][sid]) for i in range(12))
                series[sid]=returns
            assert score_args['scenario_dates']==dates[21::21]
            coordinate_checked=True
            reference=[qprices[b]/qprices[a]-1 for a,b in zip(dates,dates[1:])]
            values=[sum((F(held_weight[s])*series[s][i] for s in held),F(0)) for i in range(252)]
            admitted,exact_boundary,risk_interval=classify(values,reference,bounds(reference))
            if not admitted:failures.append('DOWNSIDE_MOMENT_EXCEEDS_QQQ')
            else:
                new_score=evaluate(chosen,score_args)
                ratio=holding_score['product']/new_score['product']
                relation='WIN' if ratio>1 else 'TIE' if ratio==1 else 'LOSE'
        records.append(dict(date=day,status=relation or 'INELIGIBLE',failure_reasons=failures,
                            actual_cash=str(actual['cash']),held_quantities=held,current_target=chosen,
                            held_stock_weights=held_weight,current_stock_weights=new_weight,
                            held_total_stock_weight=float(sum(map(F,held_weight.values()))),current_total_stock_weight=float(sum(map(F,new_weight.values()))),
                            same_quantities=held==chosen,coordinate_checked=coordinate_checked,risk_interval=risk_interval,
                            held_product_sha256=exact_hash(holding_score['product']) if holding_score else None,
                            product_ratio_sha256=exact_hash(ratio) if ratio is not None else None,
                            product_ratio_float=float(ratio) if ratio is not None else None))
    for name in verified:check(name)
    for p in [BASE/'book.json',BASE/'contract.json',Path(__file__)]:local_hashes[p.relative_to(ROOT).as_posix()]=sha256(p.read_bytes()).hexdigest()
    result=dict(status='STATIC_SAVED_PATH_SCREEN_ONLY',elapsed=time.monotonic()-started,counts=dict(Counter(r['status'] for r in records)),
                failures=dict(Counter(f for r in records for f in r['failure_reasons'])),
                changed_win_or_tie_dates=[r['date'] for r in records if r['status'] in ('WIN','TIE') and not r['same_quantities']],
                records=records,prior_expected_pins_checked=verified,local_artifact_hashes=local_hashes,
                limits=['No new selection or account replay','Monthly new risk epoch follows existing reset; no old peak/lock preserved',
                        'Exact current held shares only, never cap/clip to manufacture eligibility','No subsequent realized return conclusion'])
    (output/'result.json').write_text(dumps(result),encoding='utf8')
    print(json.dumps({k:result[k] for k in ['status','elapsed','counts','failures','changed_win_or_tie_dates']},indent=2))


if __name__=='__main__':run()
