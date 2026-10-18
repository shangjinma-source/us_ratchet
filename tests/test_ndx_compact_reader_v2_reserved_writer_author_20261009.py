"""Narrow reserved writer-path transitions; no synthetic producer authority."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
from datetime import datetime,timedelta
import unittest
from unittest.mock import patch

from scripts import ndx_registered_compact_history_independent_readback_20261009_v2 as reader
from scripts import ndx_registered_observation_independent_readback_20261009_v2 as observer
from backtest import ndx_observation_runtime_registration_research_v1 as registration
from backtest import ndx_continuation_consumer_metadata_research_v1 as metadata
from test_ndx_compact_reader_v2_optional_consumer_author_20261009 import physical_continuation_capture,pins


class ReservedWriterAuthorTests(unittest.TestCase):
    def test_one_registered_absent_writer_path_only_and_immutable_stage_guard(self):
        with TemporaryDirectory(prefix='SYNTHETIC_ONLY_R2_reserved_writer_')as directory:
            root=Path(directory);research,parent,context,args,capture=physical_continuation_capture(root,new_session=True)
            family=reader.decode(Path(args['consumer_role_registry_path']).read_bytes())
            writer=family['consumer_references']['observation_writer'];output=research/'reserved_observation'
            dependencies={key:reader.reference(*value)for key,value in observer.DEPENDENCIES.items()}
            value=dict(schema=registration.SCHEMA,runtime_reference=writer,dependency_references=dependencies,
                parent=parent,capture=capture,output_directory=str(output),**registration.FLAGS)
            path=root/'reserved_observation_registration.json';path.write_bytes(reader.encode(value));regref=reader.reference(path,reader.sha(path.read_bytes()))
            with patch.multiple(reader,RESEARCH=research,CURRENT=context['current'],**pins()):
                result=reader.verify_saved_parent_ancestry(parent_references=parent,consumer_writer_registration_reference=regref,**args)
                self.assertFalse(output.exists());self.assertEqual(result['verified_writer_registration_reference'],regref)
                self.assertEqual(result['capture_envelope']['reference'],capture['reference'])
                self.assertEqual(result['capture_plan'],reader.decode(Path(capture['reference']['path']).read_bytes())['plan'])
                self.assertFalse(any(Path(source).parent==output for source in result['writer_input_sources']))
                host=dict(bound_pair=result['bound_pair'],consumer_registry_view=result['consumer_registry_view'],
                    consumer_registry_core_reference=result['consumer_registry_core_reference'],metadata_contract_reference=result['consumer_metadata_contract_reference'])
                inputs=dict(parent=parent,capture=capture,registration=regref,runtime=writer,dependencies=dependencies,
                    auxiliary_dependencies={key:reader.reference(*value)for key,value in observer.AUXILIARY_DEPENDENCIES.items()},
                    registration_core=reader.reference(*observer.REGISTRATION_CORE),reference_core=reader.reference(*reader.REGISTRATION_CORE),
                    **metadata.continuation_input_references(registered_dependency_references=dependencies,consumer_role='observation_writer',**host))
                inventory=result['writer_prior_attempt_inventory'];view=result['parent_view']
                writer_clock=(datetime.fromisoformat(result['capture_envelope']['document']['capture_completed_at'])+timedelta(minutes=1)).isoformat()
                start=dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V5',writer_started_at_utc=writer_clock,
                    writer_adapter_schema=observer.ADAPTER,input_references=inputs,source_hashes=deepcopy(result['writer_input_sources']),
                    runtime=dict(python='synthetic declaration',executable=sys.executable,implementation='synthetic unexecuted writer'),
                    capture_checker_reference=reader.reference(*reader.AUXILIARIES['capture_checker']),attempt_inventory_scope=observer.INVENTORY_SCOPE,
                    local_attempt_namespace_inventory=inventory,actual_parent_schema=view['parent_schema'],
                    local_direct_child_inventory_scope=dict(root=str(research),depth=1,semantic_writer_namespaces_scanned=True),
                    external_parent_bound_attempt_inventory={key:value for key,value in inventory.items()if Path(key).parent.parent!=research},
                    external_unregistered_attempt_discovery_performed=False,shared_upstream_capture_checker_called=True,capture_readback_called=False,
                    independent_prefix_checker_reference=reader.reference(*reader.AUXILIARIES['independent_prefix']),producer_prefix_core_called=False,gap_core_called=False,
                    **metadata.expected_consumer_metadata(consumer_role='observation_writer',**host),**dict.fromkeys(observer.WRITER_FALSE,False))
                output.mkdir();startpath=output/'started.json';raw=reader.encode(start);startpath.write_bytes(raw);result['final_guard']()
                changed=deepcopy(start);changed['input_references']['registration']=reader.reference(root/'unknown_registration.json','a'*64)
                startpath.write_bytes(reader.encode(changed))
                with self.assertRaises(ValueError):result['final_guard']()
                startpath.write_bytes(raw);result['final_guard']()
                startpath.unlink()
                with self.assertRaises(ValueError):result['final_guard']()
                startpath.write_bytes(raw);result['final_guard']()
                extra=output/'failure.json';extra.write_bytes(b'{}')
                with self.assertRaises(ValueError):result['final_guard']()
                extra.unlink();result['final_guard']()
                neighbor=research/'unregistered_writer';neighbor.mkdir();(neighbor/'started.json').write_bytes(raw)
                with self.assertRaises(ValueError):result['final_guard']()
                (neighbor/'started.json').unlink();neighbor.rmdir();result['final_guard']()
                with self.assertRaisesRegex(ValueError,'Initial reserved writer'):
                    reader.verify_saved_parent_ancestry(parent_references=parent,consumer_writer_registration_reference=regref,**args)


if __name__=='__main__':unittest.main()
