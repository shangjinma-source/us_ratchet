"""Synthetic/temporary writer review. Never executes the actual writer."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ndx_prospective_observation_writer_v3_20261009 as writer
from test_ndx_prospective_observation_gap_parent_payload_20261009_v3 import arguments as payload_arguments


def envelope(entries=()):
    return {'document':{'history':{'observations':list(entries)}}}


def save(path,value):
    raw=writer.encode(value);path.write_bytes(raw)
    return {'path':str(path),'sha256':writer.sha(raw)}


def resolved(folder):
    folder.mkdir()
    save(folder/'started.json',{'schema':'PROSPECTIVE_OBSERVATION_WRITER_STARTED_V1'})
    payload={'schema':'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1','observation_id':'a'*64}
    payload_ref=save(folder/'observation_payload.json',payload)
    receipt_ref=save(folder/'receipt.json',{'schema':'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1',
        'observation_id':'a'*64,'payload_reference':payload_ref})
    return {'payload_reference':payload_ref,'receipt_reference':receipt_ref,'observation_id':'a'*64}


class IndependentWriterTests(unittest.TestCase):
    def test_all_future_pins_fail_before_any_io(self):
        valid={key:{'path':'synthetic/'+key,'sha256':'a'*64} for key in writer.ROLES}
        for key in (*writer.ROLES,'producer','core'):
            captures=deepcopy(valid);producer={'path':'producer','sha256':'b'*64};core={'path':'core','sha256':'c'*64}
            if key in writer.ROLES:captures[key]=None
            elif key=='producer':producer=None
            else:core=None
            with (patch.multiple(writer,CAPTURE_BOUND=captures,CAPTURE_PRODUCER=producer,CAPTURE_CORE=core),
                  patch.object(Path,'read_bytes',side_effect=AssertionError('Pending IO')),
                  patch.object(Path,'exists',side_effect=AssertionError('Pending IO')),
                  patch.object(Path,'mkdir',side_effect=AssertionError('Pending output'))):
                with self.subTest(key=key),self.assertRaises(ValueError):writer.run(execute=True)

    def test_renamed_start_only_v1_v2_v3_cannot_bypass_attempt(self):
        for version in ('V1','V2','V3'):
            with tempfile.TemporaryDirectory() as root:
                research=Path(root);folder=research/'innocent-random-name';folder.mkdir()
                save(folder/'started.json',{'schema':'PROSPECTIVE_OBSERVATION_WRITER_STARTED_'+version})
                with patch.multiple(writer,RESEARCH=research,OUTPUT=research/'new-attempt'):
                    with self.subTest(version=version),self.assertRaisesRegex(ValueError,'UNRESOLVED_PRIOR'):
                        writer.attempt_inventory(envelope(),{})

    def test_payload_only_receipt_only_failure_and_unknown_completed_attempt_block(self):
        for mode in ('payload','receipt','failure','completed'):
            with tempfile.TemporaryDirectory() as root:
                research=Path(root);folder=research/'renamed'
                if mode=='completed':resolved(folder)
                else:
                    folder.mkdir()
                    name,value={'payload':('observation_payload.json',{'schema':'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1'}),
                        'receipt':('receipt.json',{'schema':'PROSPECTIVE_OBSERVATION_DURABLE_RECEIPT_V1'}),
                        'failure':('failure.json',{'status':'FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY'})}[mode]
                    save(folder/name,value)
                with patch.multiple(writer,RESEARCH=research,OUTPUT=research/'new'):
                    with self.subTest(mode=mode),self.assertRaises(ValueError):writer.attempt_inventory(envelope(),{})

    def test_resolved_attempt_exact_bytes_and_new_partial_inventory_changes_detected(self):
        with tempfile.TemporaryDirectory() as root:
            research=Path(root);entry=resolved(research/'old');parent=envelope([entry])
            with patch.multiple(writer,RESEARCH=research,OUTPUT=research/'new'):
                before=writer.attempt_inventory(parent,{})
                self.assertEqual(len(before),1)
                extra=research/'other-name';extra.mkdir();save(extra/'started.json',{'schema':'PROSPECTIVE_OBSERVATION_WRITER_STARTED_V3'})
                with self.assertRaises(ValueError):writer.attempt_inventory(parent,{})
                (extra/'started.json').unlink();extra.rmdir()
                save(research/'old/observation_payload.json',{'schema':'PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1','observation_id':'b'*64})
                with self.assertRaises(ValueError):writer.attempt_inventory(parent,{})

    def test_research_symlink_and_evidence_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            research=Path(root)/'research';research.mkdir();target=Path(root)/'target';target.mkdir()
            link=research/'renamed'
            try:link.symlink_to(target,target_is_directory=True)
            except OSError as error:self.skipTest(str(error))
            with patch.multiple(writer,RESEARCH=research,OUTPUT=research/'new'):
                with self.assertRaises(ValueError):writer.attempt_inventory(envelope(),{})
                link.unlink();folder=research/'folder';folder.mkdir();save(target/'started.json',{'schema':'PROSPECTIVE_OBSERVATION_WRITER_STARTED_V3'})
                (folder/'started.json').symlink_to(target/'started.json')
                with self.assertRaises(ValueError):writer.attempt_inventory(envelope(),{})

    def test_private_fixed_sources_ignore_sysmodules_and_reject_drift(self):
        raw=writer.CORE.read_bytes()
        fake=SimpleNamespace(prepare_observation_payload=lambda **kwargs: (_ for _ in ()).throw(AssertionError('Fake core')))
        with patch.dict(sys.modules,{'backtest.ndx_prospective_observation_receipt_research':fake}):
            core=writer.private_module(raw,writer.CORE,writer.CORE_SHA,'_independent_fixed_payload')
            self.assertEqual(core.prepare_observation_payload.__module__,'_independent_fixed_payload')
        with self.assertRaises(ValueError):writer.private_module(raw+b'\n',writer.CORE,writer.CORE_SHA,'_changed')

    def test_save_is_durable_createonly_and_mutable_source_guard_rejects(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'started.json'
            with patch.object(writer,'resource_gate'):
                ref=writer.save(path,{'flag':False});self.assertEqual(writer.sha(path.read_bytes()),ref['sha256'])
                with self.assertRaises(FileExistsError):writer.save(path,{'flag':True})
        with patch.object(writer,'consume',side_effect=AssertionError('Mutable source read')):
            with self.assertRaisesRegex(ValueError,'mutable cache'):writer.guard({str(writer.ROOT/'data/cache/QQQ.csv'):'a'*64})

    def test_publication_crossing_deadline_records_late_and_failed_attempt_stays(self):
        core,_,args=payload_arguments();args.pop('writer_started_at_utc');args.pop('writer_completed_at_utc')
        start='2026-10-09T13:29:59+00:00';end='2026-10-09T13:29:59.1+00:00'
        claims=core.prepare_observation_payload(**args,writer_started_at_utc=start,writer_completed_at_utc=end)['source_hash_claims']
        refs={role:{key:{'path':role+'/'+key,'sha256':'a'*64} for key in writer.ROLES} for role in ('parent','capture')}
        valid={'path':'synthetic','sha256':'b'*64}
        for fail_after_payload in (False,True):
            with tempfile.TemporaryDirectory() as root:
                output=Path(root)/'attempt';calls=[]
                def guard():
                    calls.append(True)
                    if fail_after_payload and len(calls)==2:raise ValueError('Injected after payload')
                loaded=(args,refs,claims,core,guard,{}, {'path':str(writer.CHECKER),'sha256':writer.CHECKER_SHA})
                with (patch.multiple(writer,OUTPUT=output,CAPTURE_BOUND=refs['capture'],CAPTURE_PRODUCER=valid,CAPTURE_CORE=valid),
                      patch.object(writer,'load_inputs',return_value=loaded),patch.object(writer,'resource_gate'),
                      patch.object(writer,'now',side_effect=[start,end,'2026-10-09T13:30:00+00:00'])):
                    if fail_after_payload:
                        with self.assertRaisesRegex(ValueError,'Injected after payload'):writer.run(execute=True)
                        self.assertTrue((output/'observation_payload.json').is_file())
                        self.assertTrue((output/'failure.json').is_file())
                        self.assertFalse((output/'receipt.json').exists())
                    else:
                        writer.run(execute=True)
                        payload=writer.decode((output/'observation_payload.json').read_bytes())
                        receipt=writer.decode((output/'receipt.json').read_bytes())
                        self.assertEqual(payload['timing_classification'],'WITHIN_CONSERVATIVE_OBSERVATION_WINDOW')
                        self.assertEqual(receipt['timing_classification'],'LATE_OBSERVATION')
                        self.assertFalse(receipt['month_first_actual_observation'])
                    with self.assertRaisesRegex(ValueError,'Exclusive attempt'):writer.run(execute=True)

    def test_resource_stop_precedes_namespace_creation(self):
        valid={'path':'synthetic','sha256':'a'*64};refs={key:valid for key in writer.ROLES}
        with tempfile.TemporaryDirectory() as root:
            output=Path(root)/'attempt'
            with (patch.multiple(writer,OUTPUT=output,CAPTURE_BOUND=refs,CAPTURE_PRODUCER=valid,CAPTURE_CORE=valid),
                  patch.object(writer,'load_inputs',return_value=(None,)*7),
                  patch.object(writer.shutil,'disk_usage',return_value=SimpleNamespace(free=0))):
                with self.assertRaisesRegex(ValueError,'Resource stop'):writer.run(execute=True)
                self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
