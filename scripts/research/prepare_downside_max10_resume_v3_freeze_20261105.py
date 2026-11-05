"""Freeze v3 dependency/provenance closure, never execute strategy calculations."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from scripts.research.prepare_downside_max10_freeze_20261105 import dependency_closure
from docs.candidates.downside_resume_chain_20261105 import verify_parent

ROOT=Path(__file__).resolve().parents[2]


def prepare(additional_artifacts):
    prior_name='research_contracts/downside_max10_resume_20261105/freeze.json'
    prior=json.loads((ROOT/prior_name).read_bytes());pins=dict(prior['source_hashes'])
    def add(name, expected=None):
        target=(ROOT/name).resolve()
        if not target.is_relative_to(ROOT):raise ValueError('SOURCE_OUTSIDE_ROOT')
        value=sha256(target.read_bytes()).hexdigest()
        if expected is not None and value!=expected:raise ValueError('EXPECTED_SOURCE_CHANGED:'+name)
        if name in pins and pins[name]!=value:raise ValueError('PIN_CONFLICT:'+name)
        pins[name]=value
    for name,value in list(pins.items()):add(name,value)
    parent=verify_parent(ROOT,ROOT/'tmp/downside_max10_20261105_late_v2')
    for name,value in parent['file_hashes'].items():add(name,value)
    artifacts={'tmp/meta_dividend_evidence_20261105/supplement.json':'3781f42104301307194fa91d82a9db9696f0c1e2a5d7c2f47ca240c438492413'}
    for item in additional_artifacts:
        name,digest=item.rsplit('=',1)
        if name in artifacts:raise ValueError('DUPLICATE_ARTIFACT')
        artifacts[name]=digest
    if len(artifacts)<2:raise ValueError('REVIEWED_CEG_ARTIFACT_REQUIRED')
    for name,value in artifacts.items():
        add(name,value);artifact=json.loads((ROOT/name).read_bytes())
        if not artifact.get('review_rows') or len(artifact['review_rows'])!=len(artifact['dividend_events']):
            raise ValueError('ARTIFACT_SCHEMA')
        for path,digest in artifact['source_hashes'].items():add(path,digest)
    roots=['scripts/research/run_downside_account_candidate_20261105_v3.py',
           'docs/candidates/qqq_risk_budget_account_runner.py',
           'tmp/two_stage_bull_bear_20261029/wbd_local_review/legacy_absence_adapter.py']
    closure=dependency_closure(roots)
    for name in closure:add(name)
    for name in [prior_name,'scripts/research/prepare_downside_max10_resume_v3_freeze_20261105.py',
                 'docs/candidates/downside_max10_resume_v3_contract_20261105.md']:add(name)
    folder=ROOT/'research_contracts/downside_max10_resume_v3_20261105'
    folder.mkdir(exist_ok=False)
    result=dict(schema='DOWNSIDE_MAX10_RESUME_EXECUTION_V3',status='READY_FOR_FIXED_MAX10_EXECUTION',
                max_holdings=10,windows={'2024_2026':31},seconds_per_window=10800,seconds_per_month=600,
                additional_execution_artifacts=list(artifacts),source_hashes=pins,local_import_closure=sorted(closure),
                parent_output=parent['parent_path'],parent_ledger_rows=len(parent['book']['daily_ledger']),
                inherited_seconds=parent['summary']['elapsed_seconds'],inherited_searches=parent['summary']['searches'],
                scope='MULTIGENERATION_EXACT_REPLAY_AND_PAIRED_ORDINARY_DIVIDENDS_ONLY')
    (folder/'freeze.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(dict(source_pins=len(pins),parent_rows=result['parent_ledger_rows'],artifacts=list(artifacts))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--artifact',action='append',default=[])
    prepare(parser.parse_args().artifact)
