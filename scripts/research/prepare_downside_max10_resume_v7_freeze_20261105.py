"""Freeze v7 configuration/provenance closure, never execute strategy calculations."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from scripts.research.prepare_downside_max10_freeze_20261105 import dependency_closure
from docs.candidates.downside_resume_chain_20261105 import verify_parent
from docs.candidates.downside_resume_chain_20261105 import append_ordinary_artifact
from backtest.research_exact_fraction_json import loads
from scripts.run_old_continuous_probe_v4 import admit_reviewed_dividends

ROOT=Path(__file__).resolve().parents[2]


from docs.candidates.downside_absence_artifact_20261105 import append_execution_artifact
from scripts.run_old_continuous_probe_v4 import admit_period_absence
from copy import deepcopy

def verify_current_blocker_coverage(document, gate, artifacts):
    document=deepcopy(document);review=dict(rows=[],source_hashes={})
    for artifact in artifacts:append_execution_artifact(document,review,artifact)
    result=admit_period_absence(admit_reviewed_dividends(gate,review,document["dividend_events"]),review)
    if not result["admitted"]:raise ValueError("PARENT_BLOCKERS_NOT_COVERED")
    return dict(status="EXISTING_PARENT_GATE_ADMITTED",mapped=len(result["mapped_ordinary_dividends"]),remaining_events=result["unmapped_events"],remaining_streams=result["missing_action_streams"])


def prepare(additional_artifacts):
    prior_name='research_contracts/downside_max10_resume_v6_20261105/freeze.json'
    prior=json.loads((ROOT/prior_name).read_bytes());pins=dict(prior['source_hashes'])
    def add(name, expected=None):
        target=(ROOT/name).resolve()
        if not target.is_relative_to(ROOT):raise ValueError('SOURCE_OUTSIDE_ROOT')
        value=sha256(target.read_bytes()).hexdigest()
        if expected is not None and value!=expected:raise ValueError('EXPECTED_SOURCE_CHANGED:'+name)
        if name in pins and pins[name]!=value:raise ValueError('PIN_CONFLICT:'+name)
        pins[name]=value
    for name,value in list(pins.items()):add(name,value)
    parent=verify_parent(ROOT,ROOT/'tmp/downside_max10_20261105_late_v6')
    for name,value in parent['file_hashes'].items():add(name,value)
    artifacts={name:prior['source_hashes'][name] for name in prior['additional_execution_artifacts']}
    for item in additional_artifacts:
        name,digest=item.rsplit('=',1)
        if name in artifacts:raise ValueError('DUPLICATE_ARTIFACT')
        artifacts[name]=digest
    if len(artifacts)<=len(prior['additional_execution_artifacts']):raise ValueError('REVIEWED_GOOG_KDP_ARTIFACT_REQUIRED')
    artifact_documents=[]
    for name,value in artifacts.items():
        add(name,value);artifact=json.loads((ROOT/name).read_bytes())
        if not artifact.get('review_rows') or (artifact.get('schema')!='BOUNDED_PROVIDER_ABSENCE_V1' and len(artifact['review_rows'])!=len(artifact['dividend_events'])):
            raise ValueError('ARTIFACT_SCHEMA')
        for path,digest in artifact['source_hashes'].items():add(path,digest)
        artifact_documents.append(artifact)
    exposure_name='tmp/downside_max10_20261105_late_v6/2026-02-27.exposure.json'
    add(exposure_name)
    gate=loads((ROOT/exposure_name).read_bytes())
    if gate['decision_date']!='2026-02-27' or gate['missing_action_streams']:
        raise ValueError('EXACT_CURRENT_BLOCKER_SCOPE_REQUIRED')
    document=json.loads((ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json').read_bytes())
    coverage=verify_current_blocker_coverage(document,gate,artifact_documents)
    roots=['scripts/research/run_downside_account_candidate_20261105_v7.py',
           'docs/candidates/qqq_risk_budget_account_runner.py',
           'tmp/two_stage_bull_bear_20261029/wbd_local_review/legacy_absence_adapter.py']
    roots.append('scripts/research/run_downside_account_candidate_20261105_v3.py')
    closure=dependency_closure(roots)
    for name in closure:add(name)
    for name in [prior_name,'scripts/research/prepare_downside_max10_resume_v7_freeze_20261105.py',
                 'docs/candidates/downside_max10_resume_v7_contract_20261105.md']:add(name)
    folder=ROOT/'research_contracts/downside_max10_resume_v7_20261105'
    folder.mkdir(exist_ok=False)
    result=dict(schema='DOWNSIDE_MAX10_RESUME_EXECUTION_V7',status='READY_FOR_FIXED_MAX10_EXECUTION',
                max_holdings=10,windows={'2024_2026':31},seconds_per_window=10800,seconds_per_month=600,
                additional_execution_artifacts=list(artifacts),source_hashes=pins,local_import_closure=sorted(closure),
                parent_output=parent['parent_path'],parent_ledger_rows=len(parent['book']['daily_ledger']),
                inherited_seconds=parent['summary']['elapsed_seconds'],inherited_searches=parent['summary']['searches'],
                current_blocker_coverage=coverage,
                scope='MULTIGENERATION_EXACT_REPLAY_AND_PAIRED_ORDINARY_DIVIDENDS_ONLY')
    (folder/'freeze.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(dict(source_pins=len(pins),parent_rows=result['parent_ledger_rows'],artifacts=list(artifacts))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--artifact',action='append',default=[])
    prepare(parser.parse_args().artifact)
