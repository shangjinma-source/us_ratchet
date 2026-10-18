"""Synthetic V5 parent files over fully physical temporary V4/capture chains.

This is a test fixture, not a gap publisher or independent gap reader. Its
declarations never authenticate source/clock evidence. Production checkers are
used without monkeypatching, and every declared source has real immutable bytes.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from backtest import ndx_prospective_history_parent_view_research_v5 as view
from backtest import ndx_prospective_gap_history_research_v5 as gap
from backtest import ndx_accounted_source_prefix_research_v1 as prefix
from scripts import ndx_registered_forward_capture_runtime_20261009_v1 as producer
from scripts import ndx_registered_forward_capture_independent_readback_20261009_v1 as reader
import test_ndx_registered_forward_capture_runtime_20261009_v1_independent_review as physical


GAP_FILES={'started.json','history.json','publication.json','QQQ.accounted_prefix.csv',
    'SPY.accounted_prefix.csv','QQQ.prefix_evidence.json','SPY.prefix_evidence.json'}


def reference(path,raw=None):
    path=Path(path)
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()if raw is None else raw).hexdigest())


def save(path,value):
    raw=value if type(value)is bytes else producer.encode(value)
    with Path(path).open('xb')as file:file.write(raw)
    return reference(path,raw)


def envelope(refs):
    result=deepcopy(refs)
    for key,role in (('document','reference'),('publication','publication_reference'),('readback','readback_reference')):
        result[key]=json.loads(Path(refs[role]['path']).read_bytes())
    return result


def physical_gap_parent(root,research,name='synthetic_gap_v5',source_dates=('2026-10-09','2026-10-12','2026-10-13')):
    """Return real-bytes four parent refs and derivation arguments for mixed V5.

    seq70 V4 -> gap09 seq71, pending12, unfinished13. The original complete
    capture snapshots stay in their existing temporary capture namespace;
    derived prefixes/evidence have distinct roles in the seven-file gap folder.
    """
    root,research=Path(root),Path(research)
    parent=physical.compact_parent(root,research)
    prior=envelope(parent);normalized=view.inspect_parent_history_v5(prior)
    current=physical.current_files(root,parent)
    for path in current.values():
        with path.open('ab')as file:
            file.write(b''.join((day+',100,110,90,100,1000\n').encode()for day in source_dates))
    registration_path,registration_sha,_=physical.registered(root,research,parent,name+'_capture')
    with (patch.multiple(producer,RESEARCH=research,CURRENT=current),
          patch.object(producer,'now',side_effect=['2026-10-12T20:02:00+00:00','2026-10-12T20:02:01+00:00'])):
        capture=producer.run(registration_path=str(registration_path),registration_sha256=registration_sha,execute=True)
    with patch.multiple(reader,RESEARCH=research,CURRENT=current):
        capture_audit=reader.readback(registration_path=str(registration_path),registration_sha256=registration_sha,
            **capture,output_directory=str(research/(name+'_capture_audit')),execute=True)
    capture_refs=dict(reference=capture['capture_reference'],publication_reference=capture['publication_reference'],
        readback_reference=capture_audit,reader_reference=reference(reader.SOURCE))
    captured=envelope(capture_refs);document=captured['document']
    assert document['plan']['status']==('BLOCKED_SOURCE_DIAGNOSTICS'if len(source_dates)>1 else'ONE_NEW_SESSION_CAPTURE_CANDIDATE')
    output=research/name;output.mkdir();audit_output=research/(name+'_audit');audit_output.mkdir()
    source_refs={ticker:document['captured_artifacts'][ticker]for ticker in ('QQQ','SPY')}
    source_bytes={ticker:Path(item['path']).read_bytes()for ticker,item in source_refs.items()}
    days=[row['session']for row in normalized['known_typed_rows']]+['2026-10-09']
    prefixes,evidences={},{}
    for ticker in ('QQQ','SPY'):
        raw,evidence=prefix.derive_accounted_prefix(source_bytes=source_bytes[ticker],source_reference=source_refs[ticker],
            accounted_sessions=days,scope_start=days[0])
        prefixes[ticker]=save(output/(ticker+'.accounted_prefix.csv'),raw)
        evidences[ticker]=save(output/(ticker+'.prefix_evidence.json'),gap.prefix_evidence_bytes(evidence))
    tzif=document['captured_artifacts']['tzif']
    arguments=dict(parent=prior,capture_references=capture_refs,source_bytes=source_bytes,source_references=source_refs,
        accounted_baseline_bytes={t:Path(normalized['accounted_baseline_references'][t]['path']).read_bytes()for t in ('QQQ','SPY')},
        actual_baseline_bytes={t:Path(normalized['baseline_references'][t]['path']).read_bytes()for t in ('QQQ','SPY')},
        prefix_references=prefixes,prefix_evidence_references=evidences,capture_started_at=document['capture_started_at'],
        capture_completed_at=document['capture_completed_at'],tzif_bytes=Path(tzif['path']).read_bytes(),tzif_reference=tzif)
    history=gap.extend_gap_history(**arguments)
    sources=deepcopy(history['source_hashes'])
    for obj in captured['document'],captured['publication'],captured['readback']:
        for path,digest in obj['source_hashes'].items():producer.merge(sources,dict(path=path,sha256=digest))
    for module in (view,gap,prefix):producer.merge(sources,reference(module.__file__))
    fixture_publisher=save(root/(name+'_fixture_publisher.py'),b'# Synthetic fixture producer; not a production publisher.\n')
    fixture_reader=save(root/(name+'_fixture_reader.py'),b'# Synthetic fixture reader; not an independent gap reader.\n')
    producer.merge(sources,fixture_publisher);producer.merge(sources,fixture_reader)
    inputs=dict(parent=history['parent_references'],capture=history['capture_references'])
    started=save(output/'started.json',dict(schema='PROSPECTIVE_GAP_HISTORY_STARTED_V5',input_references=inputs,
        source_hashes=deepcopy(sources),**gap.FLAGS))
    producer.merge(sources,started)
    history_ref=save(output/'history.json',dict(schema=view.WRAPPER_SCHEMA,history=history,input_references=inputs,
        source_hashes=deepcopy(sources),**gap.FLAGS))
    publication_ref=save(output/'publication.json',dict(schema=view.PUBLICATION_SCHEMA,status=view.PUBLICATION_STATUS,
        history_reference=history_ref,input_references=inputs,source_hashes=deepcopy(sources),**gap.FLAGS))
    audit_sources=deepcopy(sources)
    for item in (history_ref,publication_ref,fixture_reader):producer.merge(audit_sources,item)
    save(audit_output/'started.json',dict(schema='PROSPECTIVE_GAP_HISTORY_READBACK_STARTED_V5',source_hashes=deepcopy(audit_sources),**gap.FLAGS))
    audit_ref=save(audit_output/'independent_readback.json',dict(schema=view.READBACK_SCHEMA,status=view.READBACK_STATUS,
        history_reference=history_ref,publication_reference=publication_ref,reader_sha256=fixture_reader['sha256'],input_references=inputs,
        source_hashes=audit_sources,counts=view.gap_counts(history),entire_history_independently_reconstructed=True,
        publisher_called=False,new_pure_called=False,current_live_cache_read_or_reverified=False,**gap.FLAGS))
    refs=dict(reference=history_ref,publication_reference=publication_ref,readback_reference=audit_ref,reader_reference=fixture_reader)
    view.inspect_parent_history_v5(envelope(refs))
    assert {p.name for p in output.iterdir()}==GAP_FILES
    assert {p.name for p in audit_output.iterdir()}=={'started.json','independent_readback.json'}
    for obj in envelope(refs)['document'],envelope(refs)['publication'],envelope(refs)['readback']:
        for path,digest in obj['source_hashes'].items():assert reference(path)['sha256']==digest,path
    return refs,arguments
