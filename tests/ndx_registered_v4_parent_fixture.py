"""Disposable fully registered V4 root, starting at immutable actual V3 anchors."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_prospective_observation_writer_v3_20261009 as old_writer
from scripts import ndx_registered_observation_writer_20261009_v2 as writer
from scripts import ndx_registered_observation_independent_readback_20261009_v2 as observer
from scripts import ndx_registered_compact_history_runtime_20261009_v1 as compact
from scripts import ndx_registered_compact_history_independent_readback_20261009_v1 as compact_reader
from backtest import ndx_observation_runtime_registration_research_v1 as observation_registration
from backtest import ndx_compact_history_runtime_registration_research_v1 as compact_registration
from ndx_registered_v5_parent_fixture import reference,envelope
from ndx_registered_v5_observation_fixture import _capture


def physical_registered_v4_parent(root,research):
    """Return (four_refs, context): 70 typed / 2 actual / 8 gaps, actual Oct08.

    All new artifacts are emitted by frozen registered publishers and readers.
    Only disposable RESEARCH/CURRENT and recorded clocks are patched.
    """
    root=Path(root).resolve();research=Path(research).resolve()
    if research.parent!=root or research==writer.RESEARCH.resolve() or writer.RESEARCH.resolve() in research.parents:
        raise ValueError('Disposable direct-child research directory required')
    research.mkdir(exist_ok=True)
    parent=deepcopy(old_writer.PARENT_BOUND)
    h=envelope(parent)['document']['history']
    live=root/'registered_v4_root_live';live.mkdir(exist_ok=False);current={}
    for ticker in ('QQQ','SPY'):
        current[ticker]=live/(ticker+'.csv')
        current[ticker].write_bytes(Path(h['captured_source_references'][ticker]['path']).read_bytes()+b'2026-10-08,100,110,90,100,1000\n')
    captured,capargs=_capture(root,research,parent,current,'registered_v4_root_capture',
        '2026-10-08T20:00:00+00:00','2026-10-08T20:00:01+00:00')
    value=dict(schema=observation_registration.SCHEMA,runtime_reference=reference(writer.SOURCE),
        dependency_references={key:dict(path=str(path),sha256=digest) for key,(path,digest) in writer.DEPENDENCIES.items()},
        parent=parent,capture=captured,output_directory=str(research/'registered_v4_root_observation'),**observation_registration.FLAGS)
    path=root/'registered_v4_root_observation_registration.json';path.write_bytes(writer.encode(value))
    args=dict(registration_path=str(path),registration_sha256=reference(path)['sha256'],execute=True)
    with patch.multiple(writer,RESEARCH=research,CURRENT=current),patch.object(writer,'now',side_effect=[
            '2026-10-08T20:01:00+00:00','2026-10-08T20:01:01+00:00','2026-10-08T20:01:02+00:00']):receipt=writer.run(**args)
    payload=writer.decode(Path(receipt['path']).read_bytes())['payload_reference']
    with patch.multiple(observer,RESEARCH=research,CURRENT=current):
        audit=observer.readback(registration_path=args['registration_path'],registration_sha256=args['registration_sha256'],
            payload_reference=payload,receipt_reference=receipt,execute=True)
    observation=dict(payload_reference=payload,receipt_reference=receipt,audit_reference=audit,reader_reference=reference(observer.SOURCE))
    value=dict(schema=compact_registration.SCHEMA,runtime_reference=reference(compact.SOURCE),
        dependency_references={key:dict(path=str(path),sha256=digest) for key,(path,digest) in compact.DEPENDENCIES.items()},
        parent=parent,observation=observation,output_directory=str(research/'registered_v4_root_history'),**compact_registration.FLAGS)
    path=root/'registered_v4_root_history_registration.json';path.write_bytes(compact.encode(value))
    compactargs=dict(registration_path=str(path),registration_sha256=reference(path)['sha256'],execute=True)
    with patch.object(compact,'RESEARCH',research):published=compact.run(**compactargs)
    with patch.object(compact_reader,'RESEARCH',research):
        audit=compact_reader.readback(registration_path=compactargs['registration_path'],registration_sha256=compactargs['registration_sha256'],
            history_reference=published['history_reference'],publication_reference=published['publication_reference'],
            output_directory=str(research/'registered_v4_root_history_audit'),execute=True)
    refs=dict(reference=published['history_reference'],publication_reference=published['publication_reference'],
        readback_reference=audit,reader_reference=reference(compact_reader.SOURCE))
    return refs,dict(root=root,research=research,parent=parent,capture=captured,current=current,observation=observation,
        capture_arguments=capargs,observation_arguments=args,compact_arguments=compactargs)
