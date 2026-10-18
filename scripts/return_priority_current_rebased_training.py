"""Pure current full-domain coordinate compiler and create-only saved-input CLI.

No selector, optimizer, ledger, network or account imports. Manifest authentication
and full current membership admission remain the source owner's responsibility.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from backtest.return_priority_monthly_training_inputs import compile_monthly_training_window


def prepare(data):
    """Manifest contract: decision_date, coordinate_asof_date, training_dates,
    members, candidates, source_hashes, admission. Each included candidate carries
    raw_close[253], training_source, training_rule, price_coordinate_factors,
    true_share_events, decision_nominal_close and explicit review references.
    Events here describe saved price coordinates, never executable share changes.
    """
    pins=data['source_hashes'];days=data['training_dates'];decision=data['decision_date']
    if len(days)!=253 or days!=sorted(set(days)) or days[-1]!=decision:
        raise ValueError('INVALID_253_SESSION_CALENDAR')
    for day in days:
        if date.fromisoformat(day).isoformat()!=day:raise ValueError('INVALID_DATE')
    coordinate_asof=data['coordinate_asof_date']
    if date.fromisoformat(coordinate_asof).isoformat()!=coordinate_asof or coordinate_asof<decision:
        raise ValueError('INVALID_COORDINATE_ASOF')
    members=data['members'];rows=data['candidates']
    if len(set(members))!=len(members) or len(rows)!=len(members) or {r['ticker'] for r in rows}!=set(members):
        raise ValueError('FULL_DOMAIN_MISMATCH')
    def refs(values):
        if not isinstance(values,list) or not values or any(v not in pins for v in values):
            raise ValueError('UNPINNED_COORDINATE_OR_IDENTITY_EVIDENCE')
    def positive(value):
        if isinstance(value,bool):raise ValueError('BOOLEAN_PRICE_OR_RATIO')
        result=Fraction(str(value))
        if result<=0:raise ValueError('NONPOSITIVE_PRICE_OR_RATIO')
        return result
    candidates=[]
    for original in rows:
        row=deepcopy(original)
        if row['status']=='EXCLUDED_TRAINING_RULE':
            # Existing compiler validates matured, sourced short-history exclusion.
            candidates.append(row);continue
        blockers=list(row.get('blockers',[]))
        if not row.get('identity_reviewed'):blockers.append('IDENTITY_NOT_REVIEWED')
        if not row.get('coordinate_reviewed'):blockers.append('COORDINATE_NOT_REVIEWED')
        if blockers:
            row.update(status='BLOCKED',blockers=blockers);candidates.append(row);continue
        refs(row['coordinate_source_references']);refs(row['identity_source_references'])
        if row['training_source'] not in pins:raise ValueError('UNPINNED_WHOLE_SOURCE')
        values=row['raw_close']
        if len(values)!=253:raise ValueError('RAW_CLOSE_LENGTH_MISMATCH')
        missing=[d for d,v in zip(days,values) if v is None]
        if missing:
            row.update(status='BLOCKED',blockers=['MISSING_PREDECISION_CLOSE'],missing_training_dates=missing)
            candidates.append(row);continue
        prices=[positive(v) for v in values]
        groups=[]
        for name,key in [('price_coordinate_factors','factor'),('true_share_events','ratio')]:
            events=row.get(name,[]);seen=set();parsed=[]
            for event in events:
                day=event['date']
                if date.fromisoformat(day).isoformat()!=day or day>coordinate_asof:raise ValueError('UNOBSERVED_COORDINATE_EVENT')
                if day in seen:raise ValueError('DUPLICATE_COORDINATE_EVENT')
                seen.add(day);refs(event['source_references']);parsed.append((day,positive(event[key])))
            groups.append(parsed)
        def multiplier(day,events):
            factor=Fraction(1)
            for effective,value in events:
                if day<effective:factor*=value
            return factor
        nominal=[v*multiplier(day,groups[0]) for day,v in zip(days,prices)]
        if nominal[-1]!=positive(row['decision_nominal_close']):raise ValueError('DECISION_COST_COORDINATE_MISMATCH:'+row['ticker'])
        rule=row['training_rule']
        if rule=='RESTORED_PARENT_PRICE_ONLY':
            training=[v/multiplier(day,groups[1]) for day,v in zip(days,nominal)]
        elif rule=='UNCHANGED_WHOLE_QUOTE_CLOSE':training=prices
        else:raise ValueError('UNREVIEWED_TRAINING_RULE')
        row.update(training_close=[str(v) for v in training],decision_cost=str(nominal[-1]),
            missing_training_dates=[],status='READY_CONDITIONAL',blockers=[],training_basis=rule)
        candidates.append(row)
    window=dict(decision_cutoff=decision,training_dates=list(days),candidates=candidates,member_count=len(members))
    blocked=[r['ticker'] for r in candidates if r.get('blockers')]
    arguments=None
    if not blocked:arguments=compile_monthly_training_window(window=window,source_hashes=pins,admission=data['admission'])
    return dict(schema='CURRENT_FULL_DOMAIN_REBASED_TRAINING_V1',status='BLOCKED' if blocked else 'READY_CONDITIONAL',
        window=window,search_arguments=arguments,coverage_denominator=len(members),blocked_tickers=blocked,
        source_hashes=deepcopy(pins),coordinate_asof_date=coordinate_asof,
        coordinate_semantics='N=wholequote*strict-after pricefactors. Parentpriceonly T=N/strict-after genuine share ratios. Other admitted wholequote T=raw. Coordinate factors are not executable share events.',
        research_only=True,execution_blocked=True,independent_oos=False,search_calls=0,selector_calls=0,book_calls=0)


def prepare_saved(manifest_path, output):
    root=ROOT.resolve()
    manifest=Path(manifest_path).resolve()
    manifest.relative_to(root)  # Reject manifests outside the research repository.
    data=json.loads(manifest.read_bytes())
    for p,h in data['source_hashes'].items():
        relative=Path(p)
        if relative.is_absolute() or relative.drive or '..' in relative.parts or relative.as_posix()!=p:
            raise ValueError('SOURCE_PATH_MUST_BE_REPO_RELATIVE_POSIX:'+p)
        path=(root/relative).resolve()
        path.relative_to(root)  # Also reject symlink/junction escapes.
        if hashlib.sha256(path.read_bytes()).hexdigest()!=h:raise ValueError('SOURCE_CHANGED:'+p)
    result=prepare(data)
    for p in [manifest,Path(__file__),ROOT/'backtest/return_priority_monthly_training_inputs.py']:
        result['source_hashes'][p.resolve().relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    output=Path(output)
    if output.exists():raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
    output.mkdir(parents=True)
    p=output/'prepared.json'
    with p.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,ensure_ascii=False,allow_nan=False)
    return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),status=result['status'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(prepare_saved(args.manifest,args.output)))
