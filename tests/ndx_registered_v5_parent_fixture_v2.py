"""Fully registered disposable V5 parent factory; no synthetic V5 envelopes.

Starts from the fully registered physical V4 factory, then calls immutable bound V2
capture/publisher/readers without private-code rewrites or pending-pin patches.
All created artifacts belong to the caller's temporary research directory.
"""
from copy import deepcopy
import hashlib,json
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_registered_forward_capture_runtime_20261009_v2 as capture
from scripts import ndx_registered_forward_capture_independent_readback_20261009_v2 as capture_reader
from scripts import ndx_registered_gap_history_runtime_20261009_v1 as gap
from scripts import ndx_registered_gap_history_independent_readback_20261009_v1 as gap_reader
from backtest import ndx_forward_capture_runtime_registration_research_v2 as capture_registration
from backtest import ndx_gap_runtime_registration_research_v1 as gap_registration
from ndx_registered_v4_parent_fixture import physical_registered_v4_parent


def reference(path):
    path=Path(path)
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def envelope(refs):
    result=deepcopy(refs)
    for key,role in (('document','reference'),('publication','publication_reference'),('readback','readback_reference')):
        result[key]=json.loads(Path(refs[role]['path']).read_bytes())
    return result


def physical_registered_gap_parent(root,research):
    """Return (four_refs, context) for missed09/pending12/unfinished13.

    Caller must supply a fresh temporary root and direct-child research folder.
    The context exposes the genuine V4 parent, registrations, immutable capture
    envelope, live-path diagnostics and publication refs for subsequent tests.
    """
    root=Path(root).resolve();research=Path(research).resolve()
    if research.parent!=root or research==capture.RESEARCH.resolve()or capture.RESEARCH.resolve()in research.parents:
        raise ValueError('Disposable direct-child research directory required')
    research.mkdir(exist_ok=True)
    parent,root_context=physical_registered_v4_parent(root,research)
    old=envelope(parent)['document']['history']
    live_folder=root/'registered_gap_live';live_folder.mkdir(exist_ok=False)
    current={}
    for ticker in ('QQQ','SPY'):
        baseline=Path(old['accounted_baseline_references'][ticker]['path']).read_bytes()
        suffix=b''.join((day+',100,110,90,100,1000\n').encode()for day in ('2026-10-09','2026-10-12','2026-10-13'))
        current[ticker]=live_folder/(ticker+'.csv');current[ticker].write_bytes(baseline+suffix)
    capvalue=dict(schema=capture_registration.SCHEMA,runtime_reference=reference(capture.SOURCE),
        dependency_references=capture.configured(capture.DEPENDENCIES),parent=parent,
        output_directory=str(research/'registered_gap_capture'),**capture_registration.FLAGS)
    cappath=root/'registered_gap_capture_registration.json';cappath.write_bytes(capture.encode(capvalue))
    capargs=dict(registration_path=str(cappath),registration_sha256=reference(cappath)['sha256'],execute=True)
    with patch.multiple(capture,RESEARCH=research,CURRENT=current),patch.object(capture,'now',side_effect=[
            '2026-10-12T20:02:00+00:00','2026-10-12T20:02:01+00:00']):
        captured=capture.run(**capargs)
    with patch.multiple(capture_reader,RESEARCH=research,CURRENT=current):
        audit=capture_reader.readback(registration_path=capargs['registration_path'],registration_sha256=capargs['registration_sha256'],
            **captured,output_directory=str(research/'registered_gap_capture_audit'),execute=True)
    captures=dict(reference=captured['capture_reference'],publication_reference=captured['publication_reference'],
        readback_reference=audit,reader_reference=reference(capture_reader.SOURCE))
    gapvalue=dict(schema=gap_registration.SCHEMA,runtime_reference=reference(gap.SOURCE),dependency_references=gap.configured(),
        parent=parent,capture=captures,output_directory=str(research/'registered_gap_parent'),**gap_registration.FLAGS)
    gappath=root/'registered_gap_parent_registration.json';gappath.write_bytes(gap.encode(gapvalue))
    gapargs=dict(registration_path=str(gappath),registration_sha256=reference(gappath)['sha256'],execute=True)
    with patch.multiple(gap,RESEARCH=research,CURRENT=current):published=gap.run(**gapargs)
    with patch.multiple(gap_reader,RESEARCH=research,CURRENT=current):
        readback=gap_reader.readback(registration_path=gapargs['registration_path'],registration_sha256=gapargs['registration_sha256'],
            **published,output_directory=str(research/'registered_gap_parent_audit'),execute=True)
    refs=dict(reference=published['history_reference'],publication_reference=published['publication_reference'],
        readback_reference=readback,reader_reference=reference(gap_reader.SOURCE))
    return refs,dict(root=root,research=research,root_context=root_context,parent=parent,capture=captures,current=current,
        capture_registration=reference(cappath),gap_registration=reference(gappath),capture_arguments=capargs,gap_arguments=gapargs,
        publication=published,readback=readback)
