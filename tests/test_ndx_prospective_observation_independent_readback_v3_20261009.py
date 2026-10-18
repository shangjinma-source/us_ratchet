"""Synthetic V3 observation evidence; no actual writer/readback entrypoint."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_prospective_observation_independent_readback_v3_20261009 as reader
from scripts import ndx_prospective_observation_writer_v3_20261009 as writer
from test_ndx_prospective_observation_writer_v3_20261009 import documents
from test_ndx_prospective_observation_gap_parent_payload_20261009_v3 import arguments


def evidence(root, publication='2026-10-08T20:01:02+00:00'):
    parent,capture,producer,pure=documents()
    core,data,args=arguments();args['capture']['reference']=capture['reference']
    refs=dict(parent={k:parent[k]for k in writer.ROLES},capture={k:capture[k]for k in writer.ROLES})
    sources={str(writer.SOURCE):writer.LOADED_SHA,str(writer.CORE):writer.CORE_SHA,str(writer.CHECKER):writer.CHECKER_SHA}
    for env in (parent,capture):
        for role in ('document','publication','readback'):sources.update(env[role]['source_hashes'])
        for role in writer.ROLES:sources[env[role]['path']]=env[role]['sha256']
    preview=core.prepare_observation_payload(**args);sources.update(preview['source_hash_claims'])
    checker_ref=dict(path=str(writer.CHECKER),sha256=writer.CHECKER_SHA)
    writer_times=[args.pop('writer_started_at_utc'),args.pop('writer_completed_at_utc'),publication]
    with (patch.multiple(writer,PARENT_BOUND=refs['parent'],CAPTURE_BOUND=refs['capture'],CAPTURE_PRODUCER=producer,CAPTURE_CORE=pure),patch.object(writer,'OUTPUT',root),patch.object(writer,'load_inputs',return_value=(args,refs,sources,core,lambda:None,{},checker_ref)),
          patch.object(writer,'resource_gate'),patch.object(writer,'now',side_effect=writer_times)):
        receipt_ref=writer.run(execute=True)
    payload_ref=dict(path=str(root/'observation_payload.json'),sha256=reader.sha((root/'observation_payload.json').read_bytes()))
    payload=reader.decode((root/'observation_payload.json').read_bytes());receipt=reader.decode(Path(receipt_ref['path']).read_bytes())
    started=reader.decode((root/'started.json').read_bytes())
    blobs={}
    for group in ('sources','baseline_sources'):
        for item in args['capture'][group].values():blobs[item['reference']['path']]=item['bytes']
    tz=args['capture']['tzif'];blobs[tz['reference']['path']]=tz['bytes']
    checker=reader.private_checker(Path(reader.CHECKER[0]).read_bytes())
    return dict(payload=payload,receipt=receipt,started=started,docs=dict(parent=parent,capture=capture),refs=refs,
                payload_reference=payload_ref,blobs=blobs,session=args['session'],checker=checker,inventory={}),producer,pure


class V3ObservationReadbackTests(unittest.TestCase):
    def test_all_future_anchors_fail_before_io(self):
        valid={key:dict(path='future/'+key,sha256='a'*64)for key in reader.CAPTURE_BOUND}
        for missing in (*valid,'writer','payload','receipt','producer','pure'):
            capture=deepcopy(valid);writer_pin=('future-writer','a'*64);payload=receipt='a'*64
            producer=pure=dict(path='future-code',sha256='a'*64)
            if missing in capture:capture[missing]=None
            elif missing=='writer':writer_pin=('future-writer',None)
            elif missing=='payload':payload=None
            elif missing=='receipt':receipt=None
            elif missing=='producer':producer=None
            else:pure=None
            with (patch.multiple(reader,CAPTURE_BOUND=capture,WRITER=writer_pin,PAYLOAD_SHA=payload,RECEIPT_SHA=receipt,
                                 CAPTURE_PRODUCER=producer,CAPTURE_CORE=pure),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),
                  patch.object(Path,'iterdir',side_effect=AssertionError('IO'))):
                with self.subTest(missing=missing),self.assertRaises(ValueError):reader.readback(execute=True)

    def test_full_independent_formula_keeps_gap_counts_and_month_first(self):
        with tempfile.TemporaryDirectory()as folder:
            values,producer,pure=evidence(Path(folder)/'attempt')
            with patch.multiple(reader,CAPTURE_PRODUCER=producer,CAPTURE_CORE=pure):counts=reader.inspect(**values)
            self.assertEqual(counts['parent_typed_row_count'],69)
            self.assertEqual(counts['parent_actual_observation_count'],1)
            self.assertEqual(counts['parent_gap_count'],8)
            self.assertIs(counts['month_first_actual_observation'],False)
            self.assertEqual(values['payload']['sequence'],70)

    def test_publication_deadline_crossing_is_late_receipt(self):
        with tempfile.TemporaryDirectory()as folder:
            values,producer,pure=evidence(Path(folder)/'attempt','2026-10-09T13:30:00+00:00')
            with patch.multiple(reader,CAPTURE_PRODUCER=producer,CAPTURE_CORE=pure):counts=reader.inspect(**values)
            self.assertEqual(values['payload']['timing_classification'],'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW')
            self.assertEqual(counts['timing_classification'],'LATE_OBSERVATION')
            self.assertFalse(counts['month_first_actual_observation'])

    def test_payload_receipt_and_scope_tampering_rejected(self):
        mutations={
            'ordinal':lambda v:v['payload'].update(sequence=67),
            'month':lambda v:v['receipt'].update(month_first_actual_observation=True),
            'authority':lambda v:v['payload'].update(candidate_seal_allowed=0),
            'runtime':lambda v:v['receipt']['runtime'].update(executable='other'),
            'inventory':lambda v:v['payload'].update(local_attempt_namespace_inventory={'extra':{}}),
            'checker':lambda v:v['started']['capture_checker_reference'].update(sha256='b'*64),
            'rawsource':lambda v:v['payload']['full_original_sources_preserved']['QQQ']['sources'].update(original_csv_bytes_base64='AA=='),
            'readback':lambda v:v['docs']['capture']['readback'].update(status='PASS'),
        }
        for name,mutate in mutations.items():
            with tempfile.TemporaryDirectory()as folder:
                values,producer,pure=evidence(Path(folder)/'attempt');mutate(values)
                with self.subTest(name=name),patch.multiple(reader,CAPTURE_PRODUCER=producer,CAPTURE_CORE=pure),self.assertRaises(ValueError):
                    reader.inspect(**values)

    def test_synthetic_readback_publishes_once_and_preserves_all_four_files(self):
        with tempfile.TemporaryDirectory()as folder:
            attempt=Path(folder)/'attempt';values,producer,pure=evidence(attempt)
            loaded=(values['docs'],values['refs'],values['blobs'],values['payload']['source_hashes'],values['checker'],{},lambda:None)
            with (patch.multiple(reader,BASE=attempt,CAPTURE_PRODUCER=producer,CAPTURE_CORE=pure,
                                 PAYLOAD_SHA=values['payload_reference']['sha256'],RECEIPT_SHA=reader.sha((attempt/'receipt.json').read_bytes())),
                  patch.object(reader,'load_inputs',return_value=loaded),patch.object(reader,'guard'),
                  patch.object(reader.shutil,'disk_usage',return_value=type('Disk',(),{'free':10**12})())):
                result=reader.readback(execute=True)
                report=reader.decode(Path(result['path']).read_bytes())
                self.assertEqual(report['schema'],'PROSPECTIVE_OBSERVATION_INDEPENDENT_READBACK_V3')
                self.assertEqual(report['counts']['parent_gap_count'],8)
                self.assertIs(report['writer_called'],False);self.assertIs(report['payload_core_called'],False)
                self.assertEqual({p.name for p in attempt.iterdir()},{'started.json','observation_payload.json','receipt.json','independent_readback.json'})
                with self.assertRaises(ValueError):reader.readback(execute=True)
                self.assertFalse((attempt/'failure.json').exists())

    def test_guard_rejects_changed_or_failed_immutable_source(self):
        with tempfile.TemporaryDirectory()as folder:
            source=Path(folder)/'immutable.json';source.write_bytes(b'{}')
            item=dict(path=str(source),sha256=reader.sha(b'{}'))
            reader.consume(item,{})
            source.write_bytes(b'changed')
            with self.assertRaises(ValueError):reader.consume(item,{})
            source.write_bytes(b'{}');(source.parent/'failure.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):reader.consume(item,{})

    def test_mutable_live_cache_cannot_enter_evidence(self):
        with self.assertRaises(ValueError):reader.no_live({str(reader.ROOT/'data/cache/QQQ.csv'):'a'*64})

    def test_durable_readback_save_is_createonly(self):
        with tempfile.TemporaryDirectory()as folder:
            with patch.object(reader,'BASE',Path(folder)),patch.object(reader.shutil,'disk_usage',return_value=type('Disk',(),{'free':10**12})()):
                target=Path(folder)/'saved.json';reader.save(target,{'proof':False})
                self.assertEqual(reader.decode(target.read_bytes()),{'proof':False})
                with self.assertRaises(FileExistsError):reader.save(target,{'proof':True})


if __name__=='__main__':
    unittest.main()
