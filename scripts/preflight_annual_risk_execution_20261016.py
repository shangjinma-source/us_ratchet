"""Isolated annual source closure and assembler preflight; no execute path."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from data.current_research_capital_decision_v2 import REQUIRED_PINS
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4

IMPLEMENTATIONS=(
    'backtest/current_quantity_v2_risk_next_open.py',
    'backtest/current_quantity_v2_risk_overlays.py',
    'backtest/current_quantity_v2_signal_history.py',
    'backtest/annual_risk_clock_binder.py',
    'backtest/current_quantity_v2_next_open_book.py',
    'backtest/current_quantity_v2_daily_next_open.py',
    'backtest/return_priority_monthly_quantity_provider_v4.py',
    'backtest/return_priority_monthly_execution_inputs_v4.py',
    'backtest/return_priority_monthly_execution_inputs.py',
    'scripts/preflight_annual_risk_execution_20261016.py',
)


def extend_pins(prepared, additions):
    result=deepcopy(prepared)
    pins=result['source_hashes']
    for path,digest in additions.items():
        normalized=Path(path).as_posix()
        prior=[value for key,value in pins.items() if Path(key).as_posix()==normalized]
        if any(value!=digest for value in prior):raise ValueError('SOURCE_PIN_CONFLICT:'+normalized)
        pins[normalized]=digest
    if any(path not in pins for path in REQUIRED_PINS):raise ValueError('V2_METHOD_SOURCE_PINS_REQUIRED')
    return result


def prepare(output):
    destination=(ROOT/output).resolve()
    if destination.exists() or not destination.is_relative_to(ROOT/'tmp'):
        raise ValueError('NEW_TMP_DIRECTORY_REQUIRED')
    pins={}
    def read(path,expected=None):
        path=Path(path).as_posix();raw=(ROOT/path).read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if expected is not None and expected!=digest:raise ValueError('SOURCE_DRIFT:'+path)
        if path in pins and pins[path]!=digest:raise ValueError('SOURCE_PIN_CONFLICT:'+path)
        pins[path]=digest
        return raw
    def document(path):
        data=json.loads(read(path))
        for name,digest in data.get('source_hashes',{}).items():read(name,digest)
        return data
    draft_path='tmp/annual_continuous_draft_20261016_v3/draft_prepared.json'
    draft=document(draft_path)
    clock=document('tmp/annual_risk_clock_bound_20261016_v2/manifest.json')
    read('tmp/annual_risk_clock_bound_20261016_v2/resolver_snapshots.jsonl.gz',clock['snapshot_sha256'])
    for path in ('research_contracts/daily_close_availability_assumption_20261016_v1.json',
                 'research_contracts/annual_hon_cmcsa_conditional_scope_20261016_v1.json',
                 'research_contracts/annual_wdc_conditional_model_scope_20261016_v1.json'):
        document(path)
    for path in REQUIRED_PINS+IMPLEMENTATIONS:read(path)
    launch=extend_pins(draft,pins)
    launch.update(status='SOURCE_CLOSED_PREFLIGHT_ONLY_NOT_EXECUTABLE',execution_admitted=False,
        risk_history_manifest='tmp/annual_risk_clock_bound_20261016_v2/manifest.json',
        availability_assumption='research_contracts/daily_close_availability_assumption_20261016_v1.json')
    error=None;monthly_count=0
    try:
        assembled=assemble_monthly_execution_inputs_v4(launch)
        for window in assembled['monthly_inputs']:
            if window['source_hashes']!=launch['source_hashes']:
                raise ValueError('MONTHLY_FULL_PIN_SET_MISMATCH')
        monthly_count=len(assembled['monthly_inputs'])
    except (ValueError,KeyError,TypeError) as failure:
        error=str(failure)
    # Reauthenticate exact bytes after the assembler call and before publication.
    for path,digest in list(pins.items()):read(path,digest)
    destination.mkdir()
    content=json.dumps(launch,indent=2,ensure_ascii=False).encode('utf-8')
    (destination/'launch_prepared.json').write_bytes(content)
    receipt=dict(status='BLOCKED_ASSEMBLER' if error else 'ASSEMBLER_ONLY_NO_EXECUTION',
        assembler_error=error,monthly_inputs_materialized=monthly_count,
        monthly_pin_transfer='V4 inherits full top-level source_hashes; no monthly materialization claimed while TRI blocks',
        missing_required_before=[p for p in REQUIRED_PINS if p not in draft['source_hashes']],
        required_v2_pins={p:launch['source_hashes'][p] for p in REQUIRED_PINS},
        source_hashes=launch['source_hashes'],source_count=len(launch['source_hashes']),
        launch_prepared_sha256=hashlib.sha256(content).hexdigest(),search_calls=0,book_calls=0,
        economic_execution_authorized=False,execution_admitted=False,
        future_path_guards=['TRI unresolved nominal/identity/action input is retained, never filtered',
            'Actual fractional settlement, pending rights and missing marks still checked on reached paths',
            '253 selection eligibility unchanged; risk21 histories cannot admit members',
            'Source revalidation and assembler success required again before any separately authorized run'])
    (destination/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return {k:v for k,v in receipt.items() if k not in ('source_hashes','required_v2_pins')}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    print(json.dumps(prepare(parser.parse_args().output)))
