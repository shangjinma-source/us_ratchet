"""Strict one-parent replay checks. No search, book execution, or automatic retry."""
from pathlib import Path
from hashlib import sha256
from copy import deepcopy
from backtest.research_exact_fraction_json import loads
from docs.candidates.downside_account_selection_20261105 import exact_hash


def verify_parent(root,parent):
    root=Path(root).resolve();parent=Path(parent).resolve()
    if not parent.is_relative_to(root/'tmp'):raise ValueError('PARENT_OUTSIDE_RESEARCH_TMP')
    hashes={}
    def read(name):
        p=parent/name;raw=p.read_bytes();hashes[p.relative_to(root).as_posix()]=sha256(raw).hexdigest();return loads(raw)
    contract=read('contract.json');summary=read('summary.json');book=read('book.json')
    if contract['window']!='2024_2026' or summary['status']!='BLOCKED' or book['status']!='BLOCKED':raise ValueError('FIXED_BLOCKED_LATE_PARENT_REQUIRED')
    if (contract['maximum_new_searches'],contract['seconds'],contract['monthly_seconds'],contract['max_holdings'])!=(31,10800,600,10):raise ValueError('PARENT_RULES_CHANGED')
    for name,h in contract['source_hashes'].items():
        p=(root/name).resolve()
        if not p.is_relative_to(root) or sha256(p.read_bytes()).hexdigest()!=h:raise ValueError('PARENT_SOURCE_CHANGED:'+name)
    if (contract['initial_cash'],contract['fee_bps'],contract['slippage_bps'])!=('20000','0','5'):raise ValueError('PARENT_COSTS_CHANGED')
    if (summary.get('reason')!='ORDER_PROVIDER_NOT_READY' or
        book['provider_audit'][-1].get('reason',{}).get('detail')!='BRANCH_ACTION_EXPOSURE_NOT_ADMITTED:2024-01-31'):
        raise ValueError('PARENT_BLOCK_REASON_CHANGED')
    if summary['searches']!={'new':2,'reused':0} or len(book['daily_ledger'])!=21:raise ValueError('FIXED_PARENT_PROGRESS_CHANGED')
    if not 0<=summary['elapsed_seconds']<10800:raise ValueError('INVALID_PARENT_BUDGET')
    records={}
    for p in sorted(parent.glob('*.selection.json')):
        day=p.name.removesuffix('.selection.json');record=read(p.name);sidecar=read(day+'.sidecar.json');raw=record['raw_selection']
        if raw['decision_date']!=day or record['arguments']['decision_date']!=day:raise ValueError('PARENT_DAY_BINDING')
        payload={k:v for k,v in sidecar.items() if k!='integrity_sha256'}
        if raw.get('downside_sidecar_sha256')!=sidecar.get('integrity_sha256') or exact_hash(payload)!=sidecar['integrity_sha256']:raise ValueError('PARENT_SIDECAR_INTEGRITY')
        if sidecar['evidence_binding']['research_source_hashes']!=contract['source_hashes']:raise ValueError('PARENT_SIDECAR_SOURCE_BINDING')
        records[day]=dict(selection=record,sidecar=sidecar)
    if set(records)!={'2023-12-29','2024-01-31'}:raise ValueError('PARENT_SELECTION_DOMAIN_CHANGED')
    return dict(contract=contract,summary=summary,book=book,records=records,file_hashes=hashes,parent_path=parent.relative_to(root).as_posix())


def reusable(parent,arguments):
    day=arguments['decision_date'];record=parent['records'].get(day)
    if record is None:return None
    if record['selection']['arguments']!=arguments:raise ValueError('PARENT_FULL_ARGUMENTS_MISMATCH:'+day)
    return deepcopy(record)


def verify_prefix(parent_book,new_book):
    prefix=parent_book['daily_ledger'];actual=new_book['daily_ledger']
    if len(actual)<len(prefix) or actual[:len(prefix)]!=prefix:raise ValueError('PARENT_LEDGER_PREFIX_CHANGED')
    return len(prefix)


def verify_prefix_progress(parent_book,observed_ledger):
    expected=parent_book['daily_ledger'];size=min(len(expected),len(observed_ledger))
    if observed_ledger[:size]!=expected[:size]:raise ValueError('PARENT_LEDGER_PREFIX_CHANGED')
    return len(observed_ledger)>=len(expected)
