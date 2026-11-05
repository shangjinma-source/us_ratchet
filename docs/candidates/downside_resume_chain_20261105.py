"""Read-only multi-generation resume provenance; no execution or budget reset."""
from pathlib import Path
from hashlib import sha256
from copy import deepcopy
from backtest.research_exact_fraction_json import loads
from docs.candidates.downside_account_selection_20261105 import exact_hash
from docs.candidates.downside_resume_parent_20261105 import verify_prefix, verify_prefix_progress


def verify_parent(root, parent, seen=()):
    root=Path(root).resolve();parent=Path(parent).resolve()
    if not parent.is_relative_to(root/'tmp') or parent in seen or len(seen)>=8:
        raise ValueError('INVALID_PARENT_CHAIN_PATH_OR_CYCLE')
    hashes={}
    def read(name):
        p=parent/name;raw=p.read_bytes();hashes[p.relative_to(root).as_posix()]=sha256(raw).hexdigest()
        return loads(raw)
    contract=read('contract.json');summary=read('summary.json');book=read('book.json')
    if contract['window']!='2024_2026' or summary['status']!='BLOCKED' or book['status']!='BLOCKED':
        raise ValueError('BLOCKED_LATE_PARENT_REQUIRED')
    if (contract['maximum_new_searches'],contract['seconds'],contract['monthly_seconds'],contract['max_holdings'])!=(31,10800,600,10):
        raise ValueError('PARENT_RULES_CHANGED')
    if (contract['initial_cash'],contract['fee_bps'],contract['slippage_bps'])!=('20000','0','5'):
        raise ValueError('PARENT_COSTS_CHANGED')
    for name,h in contract['source_hashes'].items():
        p=(root/name).resolve()
        if not p.is_relative_to(root) or sha256(p.read_bytes()).hexdigest()!=h:
            raise ValueError('PARENT_SOURCE_CHANGED:'+name)
    if summary['reason']!='ORDER_PROVIDER_NOT_READY' or not book['provider_audit'][-1].get('reason',{}).get('detail','').startswith('BRANCH_ACTION_EXPOSURE_NOT_ADMITTED:'):
        raise ValueError('PARENT_BLOCK_REASON_NOT_ACTION_GATE')
    if summary['completed_sessions']!=len(book['daily_ledger']) or not 0<=summary['elapsed_seconds']<10800:
        raise ValueError('PARENT_PROGRESS_OR_BUDGET')
    ancestor=None
    if contract.get('parent_output'):
        ancestor=verify_parent(root,root/contract['parent_output'],seen+(parent,))
        if contract['parent_file_hashes']!=ancestor['file_hashes']:
            raise ValueError('PARENT_CHAIN_RECEIPT_CHANGED')
        if contract['inherited_seconds']!=ancestor['summary']['elapsed_seconds'] or contract['inherited_searches']!=ancestor['summary']['searches']:
            raise ValueError('INHERITED_BUDGET_CHANGED')
        if summary['elapsed_seconds']<contract['inherited_seconds']:
            raise ValueError('ELAPSED_BUDGET_RESET')
        verify_prefix(ancestor['book'],book)
        hashes.update(ancestor['file_hashes'])
    records={}
    inherited={} if ancestor is None else ancestor['records']
    for path in sorted(parent.glob('*.selection.json')):
        day=path.name.removesuffix('.selection.json');selection=read(path.name);sidecar=read(day+'.sidecar.json')
        raw=selection['raw_selection']
        if raw['decision_date']!=day or selection['arguments']['decision_date']!=day:
            raise ValueError('PARENT_DAY_BINDING')
        if exact_hash({k:v for k,v in sidecar.items() if k!='integrity_sha256'})!=sidecar['integrity_sha256'] or raw.get('downside_sidecar_sha256')!=sidecar['integrity_sha256']:
            raise ValueError('PARENT_SIDECAR_INTEGRITY')
        if day in inherited:
            old=inherited[day]
            if selection!=old['selection'] or sidecar!=old['sidecar']:
                raise ValueError('COPIED_ANCESTOR_RECORD_CHANGED')
            source_pins=old['source_pins'];origin=old['origin']
        else:
            source_pins=contract['source_hashes'];origin=parent.relative_to(root).as_posix()
        if sidecar['evidence_binding']['research_source_hashes']!=source_pins:
            raise ValueError('GENERATION_SIDECAR_SOURCE_BINDING')
        records[day]=dict(selection=selection,sidecar=sidecar,source_pins=source_pins,origin=origin)
    if not set(inherited)<=set(records):
        raise ValueError('ANCESTOR_RECORD_LOST')
    budget=summary['searches'];old_new=ancestor['summary']['searches']['new'] if ancestor else 0
    if budget['new']!=old_new+len(set(records)-set(inherited)) or not 0<=budget['new']<=31 or budget['reused']!=0:
        raise ValueError('CUMULATIVE_SEARCH_COUNT_MISMATCH')
    return dict(contract=contract,summary=summary,book=book,records=records,file_hashes=hashes,
                parent_path=parent.relative_to(root).as_posix(),chain_depth=1+(ancestor['chain_depth'] if ancestor else 0))


def reusable(parent,arguments):
    record=parent['records'].get(arguments['decision_date'])
    if record is None:return None
    if record['selection']['arguments']!=arguments:
        raise ValueError('PARENT_FULL_ARGUMENTS_MISMATCH:'+arguments['decision_date'])
    return deepcopy(record)


def append_ordinary_artifact(document,review,artifact):
    """Only paired reviewed USD dividends; ratio/conversion cannot enter here."""
    from fractions import Fraction as F
    rows,events=artifact['review_rows'],artifact['dividend_events']
    if not rows or len(rows)!=len(events):raise ValueError('PAIRED_ORDINARY_ARTIFACT_REQUIRED')
    for row,event in zip(rows,events):
        sid=row['security_id'];day=row['ex_date']
        if (row['status']!='REVIEWED_ORDINARY_CASH_DIVIDEND' or sid!=event['security_id'] or day!=event['ex_date']
            or row['payment_date']!=event['payment_date'] or row['payment_date']<day
            or F(row['amount_per_share'])!=F(event['amount_per_share']) or F(event['amount_per_share'])<=0
            or row['currency']!=event['currency'] or row['currency']!='USD' or F(event['withholding_rate'])!=0):
            raise ValueError('ORDINARY_PAIR_FIELDS')
        if any(e['security_id']==sid and e['ex_date']==day for e in document['dividend_events']):
            raise ValueError('DUPLICATE_ORDINARY_EVENT')
        ticker=document['prepared_input_candidate']['metadata'][sid]['ticker']
        observed=[e for e in document['provider_event_inventory'] if e['ticker']==ticker and e['kind']=='dividends' and e['date']==day]
        if not observed or row['observed_provider_events']!=observed:raise ValueError('EXACT_PROVIDER_INVENTORY_REQUIRED')
        if not row['source_references'] or any(ref not in artifact['source_hashes'] for ref in row['source_references']):
            raise ValueError('ORDINARY_SOURCE_PIN_REQUIRED')
        review['rows'].append(deepcopy(row));document['dividend_events'].append(deepcopy(event))
    for name,h in artifact['source_hashes'].items():
        if name in review['source_hashes'] and review['source_hashes'][name]!=h:raise ValueError('ARTIFACT_PIN_CONFLICT')
        review['source_hashes'][name]=h
