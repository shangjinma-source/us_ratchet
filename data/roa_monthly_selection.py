"""Frozen ROA selector on completed, hash-bound monthly inputs; no publication side effects."""
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

from data.roa_monthly_loader import RoaMonthlySelectionLoader


def _read(root,name,pins,expected=None):
    path=(root/name).resolve()
    if not path.is_relative_to(root):raise ValueError('MONTH_SOURCE_PATH_INVALID')
    raw=path.read_bytes();digest=sha256(raw).hexdigest()
    if expected is not None and digest!=expected:raise ValueError('MONTH_SOURCE_CHANGED:'+str(name))
    pins[str(path.relative_to(root))]=digest
    return raw


def generate_month_selection(*,root,manifest_path,manifest_sha256,calendar_sessions,completed_through,
                             facts_directory='data/cache/candidate_pools/ndx_fundamentals/raw_companyfacts'):
    # Research selector dependencies are offline generation only, not runtime loading.
    from scripts.research.describe_annual_quality_local_20261106 import select,cik_matches
    from scripts.research.screen_profitability_roa_continuous_20261106 import build_decision
    root=Path(root).resolve();pins={}
    manifest=json.loads(_read(root,manifest_path,pins,manifest_sha256))
    day=manifest['decision_date'];dates=manifest['training_dates']
    sessions=sorted(set(calendar_sessions))
    if sessions!=list(calendar_sessions):raise ValueError('MONTH_CALENDAR_INVALID')
    if day not in sessions or day>completed_through:raise ValueError('WAIT_COMPLETED_MONTH_END')
    following=next((d for d in sessions if d>day),None)
    if following is None or following[:7]==day[:7]:raise ValueError('NOT_VERIFIED_MONTH_END')
    if len(dates)!=253 or dates!=sorted(set(dates)) or dates[-1]!=day:raise ValueError('MONTH_TRAINING_WINDOW_INVALID')
    expected_window=[d for d in sessions if d<=day][-253:]
    if len(expected_window)!=253:raise ValueError('WAIT_FULL_TRAINING_CALENDAR')
    if dates!=expected_window:raise ValueError('MONTH_TRAINING_CALENDAR_MISMATCH')
    for name,expected in manifest['source_hashes'].items():_read(root,name,pins,expected)
    year=int(day[:4]);quarters=[f'{year}-{m:02d}-{last}' for m,last in ((3,'31'),(6,'30'),(9,'30'),(12,'31'))]
    cutoff=max([f'{year-1}-12-31']+[d for d in quarters if d<=day])
    ranked=[];financial=[];seen=set()
    for candidate in manifest['candidates']:
        sid=candidate['security_id'];issuer=candidate['issuer_id']
        if sid in seen:raise ValueError('MONTH_DUPLICATE_SID')
        seen.add(sid)
        if candidate['status']!='READY_CONDITIONAL' or not candidate['identity_reviewed'] or not candidate['coordinate_reviewed']:
            raise ValueError('MONTH_CANDIDATE_NOT_ADMITTED:'+sid)
        prices=list(map(Fraction,candidate['raw_close']))
        if len(prices)!=253 or any(p<=0 for p in prices):raise ValueError('MONTH_TRAINING_PRICE_INVALID')
        ranked.append(dict(security_id=sid,issuer_id=issuer,ticker=candidate['ticker'],ratio_exact=str(prices[-22]/prices[-253])))
        row=dict(security_id=sid,status='ISSUER_CIK_UNAVAILABLE')
        if issuer.startswith('issuer:') and issuer[7:].isdigit():
            name=str(Path(facts_directory)/('CIK'+issuer[7:]+'.json'))
            if not (root/name).is_file():row['status']='COMPANYFACTS_MISSING'
            else:
                facts=json.loads(_read(root,name,pins),parse_float=Decimal)
                if not cik_matches(issuer[7:],facts.get('cik')):row['status']='CIK_MISMATCH'
                else:row.update(select(facts.get('facts',{}).get('us-gaap',{}),{},cutoff))
        financial.append(row)
    ranked.sort(key=lambda r:(-Fraction(r['ratio_exact']),r['security_id']))
    for index,row in enumerate(ranked,1):row['rank']=index
    selection=build_decision(dict(decision_date=day,ranked=ranked),dict(results=[dict(cutoff=cutoff,rows=financial)]),'PROFITABLE')
    securities=[{k:r[k] for k in ('security_id','ticker','issuer_id')} for r in selection['selected']]
    for name in ('data/roa_monthly_selection.py','scripts/research/describe_annual_quality_local_20261106.py',
                 'scripts/research/screen_profitability_roa_continuous_20261106.py'):
        _read(root,name,pins)
    result=dict(schema='ROA_MONTH_SELECTION_V1',decision_date=day,effective_month=following[:7],
        first_execution_session=following,financial_cutoff=cutoff,selection=selection,
        securities=securities,weights={r['security_id']:'1/10' for r in securities},
        source_hashes=pins,financial_rows=financial,executable=False,
        limitations=['Conditional historical raw financial revisions remain; not complete PIT certification',
                     'Monthly identity/actions, market signal, real holdings and fresh quotes remain separate admission requirements'])
    result['selection_id']=sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return result


