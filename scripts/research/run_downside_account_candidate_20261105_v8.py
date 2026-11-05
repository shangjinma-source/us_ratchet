"""Configuration-only ASML final accounting continuation using the immutable v3 implementation."""
import argparse
import importlib.util
from hashlib import sha256
from pathlib import Path
import json
from docs.candidates.downside_absence_artifact_20261105 import append_execution_artifact

ROOT=Path(__file__).resolve().parents[2]
RUNNER='scripts/research/run_downside_account_candidate_20261105_v8.py'
IMPLEMENTATION='scripts/research/run_downside_account_candidate_20261105_v3.py'
FREEZE='research_contracts/downside_max10_resume_v8_20261105/freeze.json'


def validate_execution_freeze(root):
    root=Path(root).resolve();freeze=json.loads((root/FREEZE).read_bytes())
    if (freeze.get('schema')!='DOWNSIDE_MAX10_RESUME_EXECUTION_V8' or
        freeze.get('status')!='READY_FOR_FIXED_MAX10_EXECUTION' or freeze.get('max_holdings')!=10 or
        freeze.get('windows')!={'2024_2026':31} or freeze.get('seconds_per_window')!=10800 or
        freeze.get('seconds_per_month')!=600):raise ValueError('EXECUTION_FREEZE_RULES')
    pins=freeze['source_hashes']
    if RUNNER not in pins or IMPLEMENTATION not in pins:raise ValueError('ENTRY_AND_IMPLEMENTATION_PINS_REQUIRED')
    for name,h in pins.items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or sha256(path.read_bytes()).hexdigest()!=h:raise ValueError('SOURCE_CHANGED:'+name)
    return freeze


def run(window,output,parent_output):
    validate_execution_freeze(ROOT)
    spec=importlib.util.spec_from_file_location('isolated_downside_v8_v3_implementation',ROOT/IMPLEMENTATION)
    implementation=importlib.util.module_from_spec(spec);spec.loader.exec_module(implementation)
    # Only this newly loaded private module gets the new freeze reader. The v3
    # source and any running v3 namespace remain untouched; accounting is identical.
    implementation.validate_execution_freeze=validate_execution_freeze
    implementation.append_ordinary_artifact=append_execution_artifact
    return implementation.run(window,output,parent_output)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--window',choices=['2024_2026'],required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--parent-output',required=True)
    args=parser.parse_args();run(args.window,args.output,args.parent_output)
