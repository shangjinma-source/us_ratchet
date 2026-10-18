"""Read-only recovery of the preserved control receipt; never repeats execution."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_historical_single_window_accounts_20260920 as original
from backtest import ndx_fixed_control_accounting_independent_audit_v2_research as oracle

BASE=ROOT/'data/cache/research'
OLD=BASE/'historical_single_window_accounts_20260920_v1/incumbent'
OUTPUT=BASE/'historical_single_window_accounts_20260923_control_recovery_v2/account.json'
REFS={name:dict(path=str(OLD/file),sha256=sha) for name,file,sha in (
    ('raw','raw_execution.json','149aa072ae6f086f45f2fe07859163d78710f35856038f062e6e475b5bf48865'),
    ('started','started.json','d722d99538b4034481110baf2a27fa9e462002da6764ad70e3921bd7708c2f34'),
    ('failure','failure.json','f8d670dfd101ad9c6284d742d981cb87d5684685690946f7c53009dc3baa6a83'))}
LOADED={str(Path(__file__).resolve()):hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    str(Path(original.__file__).resolve()):'41cf0e15058b464d81b5977d3fa224608f1621abf77e9defa96ad938aec2964f',
    str(Path(oracle.__file__).resolve()):'dd66c787bd8e8b2cad0c14df25e88ecc7e04d502f19515072e4fa51a783140e7'}


def exact(a,b):return original.target_reader.exact(a,b)


def inspect_receipts(state,raw,started,failure):
    expected_start=dict(schema='HISTORICAL_SINGLE_WINDOW_ACCOUNT_ATTEMPT_V1',track='incumbent',attempt_count=1,
        prepared_sha256=original.digest(state),input_reference=original.INPUT,target_reference=original.TARGET,
        independent_target_audit_reference=state['independent_target_audit_reference'])
    if not exact(started,expected_start):raise ValueError('Original prepared state does not match exclusive attempt')
    expected_raw=dict(schema='HISTORICAL_SINGLE_WINDOW_RAW_EXECUTION_V1',track='incumbent',execution=raw['execution'],started_reference=REFS['started'],
        original_schedule=state['selected']['original_schedule'],internal_columns=state['selected']['columns'],calendar=state['calendar'],
        execution_contract=state['contract'],independent_accounting_completed=False,**dict.fromkeys(original.FALSE,False))
    expected_failure=dict(schema='HISTORICAL_SINGLE_WINDOW_FAILED_ATTEMPT_V1',track='incumbent',started_reference=REFS['started'],
        raw_execution_reference=REFS['raw'],engine_call_started=True,error_type='ValueError',automatic_retry_allowed=False,
        failure_is_economic_infeasibility=False,**dict.fromkeys(original.FALSE,False))
    if not exact(raw,expected_raw) or not exact(failure,expected_failure):raise ValueError('Exact original raw receipt and failure required')
    value=deepcopy(raw['execution']);selected=state['selected'];columns=selected['columns'];labels=selected['labels']
    for decision in value['decisions']:
        for sid,row in decision['targets'].items():
            if row['ticker']!=columns[sid]:raise ValueError('Internal decision label differs')
            row['ticker']=labels[sid]['ticker']
    for row in value['trades']:
        sid=row['security_id']
        if row['ticker']!=columns[sid]:raise ValueError('Internal trade label differs')
        row['ticker']=labels[sid]['ticker']
    for row in value['daily']:
        if row['tickers']!={sid:columns[sid] for sid in row['shares']}:raise ValueError('Internal daily labels differ')
        row['tickers']={sid:labels[sid]['ticker'] for sid in row['shares']}
    audit=oracle.audit(execution=value,calendar=state['calendar'],schedule=selected['original_schedule'],prices=selected['prices'],
        risk_chains_by_decision=selected['arguments']['risk_chains_by_decision'],contract=state['contract'])
    return value,audit


def build():
    original.verify_sources(LOADED)
    state=original.prepare('incumbent')  # Input reconstruction only; run/engine are never called.
    sources=dict(state['historical_expected_source_hashes']);original.archive.merge(sources,LOADED)
    docs={key:original.target_reader.read(ref,sources) for key,ref in REFS.items()}
    original.verify_sources(sources)
    execution,audit=inspect_receipts(state,docs['raw'],docs['started'],docs['failure'])
    return dict(schema='HISTORICAL_SINGLE_WINDOW_CONDITIONAL_ACCOUNT_RAW_RECOVERY_V2',track='incumbent',execution=execution,
        independent_decimal_accounting=audit,calendar=state['calendar'],schedule=state['selected']['original_schedule'],
        effective_schedule=state['effective_schedule'],normalization_evidence=state['normalization_evidence'],execution_contract=state['contract'],
        internal_columns=state['selected']['columns'],input_reference=original.INPUT,target_reference=original.TARGET,
        independent_target_audit_reference=state['independent_target_audit_reference'],started_reference=REFS['started'],raw_execution_reference=REFS['raw'],
        original_execution_source_hashes=state['historical_expected_source_hashes'],historical_expected_source_hashes=sources,
        archive_resolution=original.verify_sources(sources),prepared_sha256=original.digest(state),execution_performed=True,risk_is_order_gate=False,
        recovery_failure_reference=REFS['failure'],read_only_raw_recovery=True,execution_replayed=False,
        scope='CONDITIONAL_HISTORICAL_MECHANICAL_STRUCTURE_NOT_WINNER',**dict.fromkeys(original.FALSE,False))


def publish_verified(value):
    if not exact(value,build()):raise ValueError('Full raw recovery does not reproduce')
    saved=original.exclusive_publish(OUTPUT,value)
    if not exact(original.verify_sources(value['historical_expected_source_hashes']),value['archive_resolution']):raise ValueError('Recovery source drift')
    return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    report=build()
    print(json.dumps(publish_verified(report) if args.publish else dict(read_only_recovery_verified=True,execution_replayed=False,audit=report['independent_decimal_accounting'])))
