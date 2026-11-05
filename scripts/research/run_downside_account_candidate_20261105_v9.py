"""Configuration-only GEHC accounting-only continuation using the immutable v3 implementation."""
import argparse
import importlib.util
from hashlib import sha256
from pathlib import Path
import json
from docs.candidates.downside_absence_artifact_20261105 import append_execution_artifact

ROOT=Path(__file__).resolve().parents[2]
RUNNER='scripts/research/run_downside_account_candidate_20261105_v9.py'
IMPLEMENTATION='scripts/research/run_downside_account_candidate_20261105_v3.py'
FREEZE='research_contracts/downside_max10_resume_v9_20261105/freeze.json'


def validate_execution_freeze(root):
    root=Path(root).resolve();freeze=json.loads((root/FREEZE).read_bytes())
    if (freeze.get('schema')!='DOWNSIDE_MAX10_RESUME_EXECUTION_V9' or
        freeze.get('status')!='READY_FOR_FIXED_MAX10_EXECUTION' or freeze.get('max_holdings')!=10 or
        freeze.get('windows')!={'2024_2026':31} or freeze.get('seconds_per_window')!=10800 or
        freeze.get('seconds_per_month')!=600):raise ValueError('EXECUTION_FREEZE_RULES')
    pins=freeze['source_hashes']
    if RUNNER not in pins or IMPLEMENTATION not in pins:raise ValueError('ENTRY_AND_IMPLEMENTATION_PINS_REQUIRED')
    for name,h in pins.items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or sha256(path.read_bytes()).hexdigest()!=h:raise ValueError('SOURCE_CHANGED:'+name)
    if freeze.get("inherited_searches",{}).get("new")!=31 or freeze.get("parent_ledger_rows")!=625:
        raise ValueError("EXACT_ACCOUNTING_ONLY_PARENT_REQUIRED")
    return freeze


def reject_new_search(**arguments):
    raise ValueError("ACCOUNTING_ONLY_NO_NEW_SEARCH")


def load_accounting_only_implementation():
    spec=importlib.util.spec_from_file_location('isolated_downside_v9_v3_implementation',ROOT/IMPLEMENTATION)
    implementation=importlib.util.module_from_spec(spec);spec.loader.exec_module(implementation)
    # Only this newly loaded private module gets the new freeze reader. The v3
    # source and any running v3 namespace remain untouched; accounting is identical.
    implementation.validate_execution_freeze=validate_execution_freeze
    implementation.append_ordinary_artifact=append_execution_artifact
    implementation.decide_observed_for_account=reject_new_search
    return implementation


def run(window,output,parent_output):
    validate_execution_freeze(ROOT)
    implementation=load_accounting_only_implementation()
    return implementation.run(window,output,parent_output)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--window',choices=['2024_2026'],required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--parent-output',required=True)
    args=parser.parse_args();run(args.window,args.output,args.parent_output)
