"""SGEN-only bounded retrospective action review, not exhaustive certification."""
import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ARTIFACT='tmp/momentum_sgen_action_20261105/supplement.json'
ARTIFACT_SHA256='55e2a23e6e4069a742a82c191b480227abebc6c65c2f8a56f122711e545bb94e'
SID='research:security:sgen'


def load_artifact():
    raw=(ROOT/ARTIFACT).read_bytes()
    if sha256(raw).hexdigest()!=ARTIFACT_SHA256:
        raise ValueError('SGEN_ARTIFACT_CHANGED')
    artifact=json.loads(raw)
    for name,digest in artifact['source_hashes'].items():
        if sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('SGEN_SOURCE_CHANGED:'+name)
    return artifact


def install(document):
    artifact=load_artifact()
    for key in ('actions','provider_actions'):
        events=document['assembled'][key]
        existing=[e for e in events if e.get('security_id')==SID]
        if existing and existing!=[artifact['execution_event']]:
            raise ValueError('SGEN_EXISTING_ACTION_CONFLICT')
        if not existing:
            events.append(deepcopy(artifact['execution_event']))
    return dict(artifact['source_hashes'], **{ARTIFACT:ARTIFACT_SHA256})


def admit(gate, execution_events):
    artifact=load_artifact()
    result=deepcopy(gate)
    if SID not in result['exposed']:
        return result
    start=result['decision_date'];end=result['exposure_end_by_security'][SID]
    covered=[r for r in artifact['periods'] if r['start_exclusive']==start and end<=r['end_inclusive']]
    if len(covered)!=1:
        raise ValueError('SGEN_OUTSIDE_REVIEWED_EXPOSURE')
    expected=artifact['execution_event']
    needs_merger=start<expected['date']<=end
    if needs_merger and [e for e in execution_events if e.get('security_id')==SID]!=[expected]:
        raise ValueError('SGEN_EXACT_CASH_MERGER_EXECUTION_REQUIRED')
    remaining=[]
    for event in result['unmapped_events']:
        if event.get('security_id')!=SID:
            remaining.append(event)
        elif not (needs_merger and event==artifact['observed_barrier']):
            raise ValueError('SGEN_UNREVIEWED_ACTION')
    result['unmapped_events']=remaining
    result['missing_action_streams']=[s for s in result['missing_action_streams'] if s!=SID]
    result['accepted_sgen_conditional_review']=dict(period=covered[0],merger=expected if needs_merger else None,
                                                   limitation=artifact['limitation'])
    result['admitted']=not result['missing_action_streams'] and not remaining
    return result
