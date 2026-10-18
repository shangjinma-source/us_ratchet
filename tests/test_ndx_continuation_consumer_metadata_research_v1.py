"""Pure metadata association tests using real inspected pair/consumer views.

No source or wrapper authenticity, physical IO or continuation run is claimed.
"""
from copy import deepcopy
import hashlib
import unittest
from unittest.mock import patch

from backtest import ndx_compact_implementation_pair_binding_research_v1 as pair_kernel
from backtest import ndx_continuation_consumer_role_registry_research_v1 as consumer_kernel
from backtest import ndx_continuation_consumer_metadata_research_v1 as metadata

CONSUMER_CORE_SHA='184479c5e0e6412265e00cc875af1f7902e4f500dc984ca2aaaf3251bc8c433b'


def reference(name,digest=None):
    return dict(path='E:/synthetic/metadata/'+name+'.json',sha256=digest or hashlib.sha256(name.encode()).hexdigest())


def host_context():
    algorithms={role:{key:reference('algorithm_'+key)for key in roles}for role,roles in pair_kernel.DEPENDENCY_ROLES.items()}
    binding=dict(schema=pair_kernel.SCHEMA,family=pair_kernel.FAMILY,protocol=pair_kernel.PROTOCOL,role=pair_kernel.ROLE,
        publisher_reference=reference('publisher'),independent_reader_reference=reference('independent_reader'),
        contract_reference=reference('contract'),publisher_dependency_references=deepcopy(algorithms['publisher']),
        reader_dependency_references=deepcopy(algorithms['independent_reader']),approved_legacy_binding_references=[],**pair_kernel.FLAGS)
    pair=pair_kernel.inspect_pair_binding(binding=binding,binding_reference=reference('binding'),host_binding_reference=reference('binding'),
        self_role='independent_reader',self_reference=reference('independent_reader'),expected_contract_reference=reference('contract'),
        expected_algorithm_dependencies=algorithms)
    registry=dict(schema=consumer_kernel.SCHEMA,family=consumer_kernel.FAMILY,protocol=consumer_kernel.PROTOCOL,role=consumer_kernel.ROLE,
        implementation_pair_binding_reference=pair['binding_reference'],ancestry_contract_reference=pair['contract_reference'],
        consumer_references={role:reference('consumer_'+role)for role in consumer_kernel.CONSUMER_ROLES},**consumer_kernel.FLAGS)
    view=consumer_kernel.inspect_consumer_roles(registry=registry,registry_reference=reference('registry'),
        host_registry_reference=reference('registry'),bound_pair=pair)
    return dict(bound_pair=pair,consumer_registry_view=view,
        consumer_registry_core_reference=reference('consumer_core',CONSUMER_CORE_SHA),metadata_contract_reference=reference('metadata_core'))


def dependencies(role):
    # These host-provided original algorithm declarations remain unchanged;
    # consumer implementation roles are always separate references.
    return {key:reference('original_business_'+key)for key in metadata.REGISTERED_DEPENDENCY_ROLES[role]}


def public_inputs(role,context=None):
    context=host_context()if context is None else context
    deps=dependencies(role)
    extensions=metadata.continuation_input_references(registered_dependency_references=deps,consumer_role=role,**context)
    return dict(parent=reference('true_parent'),runtime=context['consumer_registry_view']['consumer_references'][role],
        dependencies=deepcopy(deps),**extensions),deps,context


class ContinuationMetadataAuthorTests(unittest.TestCase):
    def test_six_fixed_adapters_eight_metadata_fields_and_no_io(self):
        context=host_context();original=deepcopy(context)
        expected_adapters={
            'capture_publisher':'CONTINUATION_CAPTURE_PUBLISHER_V1',
            'capture_independent_reader':'CONTINUATION_CAPTURE_INDEPENDENT_READER_V1',
            'observation_writer':'CONTINUATION_OBSERVATION_WRITER_V1',
            'observation_independent_reader':'CONTINUATION_OBSERVATION_INDEPENDENT_READER_V1',
            'gap_publisher':'CONTINUATION_GAP_PUBLISHER_V1',
            'gap_independent_reader':'CONTINUATION_GAP_INDEPENDENT_READER_V1'}
        self.assertEqual(metadata.ADAPTERS,expected_adapters)
        with patch('builtins.open',side_effect=AssertionError('Metadata kernel must not perform IO')), \
                patch('pathlib.Path.read_bytes',side_effect=AssertionError('No source bytes')), \
                patch('pathlib.Path.write_bytes',side_effect=AssertionError('No output bytes')):
            for role,adapter in expected_adapters.items():
                value=metadata.expected_consumer_metadata(consumer_role=role,**context)
                self.assertEqual(len(value),8);self.assertEqual(set(value),set(metadata.METADATA_KEYS))
                self.assertEqual(value['consumer_role'],role);self.assertEqual(value['continuation_adapter_schema'],adapter)
                result=metadata.inspect_consumer_metadata(dict(schema='OUTER_SCHEMA_REMAINS_AN_IO_OBLIGATION',**value),expected_role=role,**context)
                self.assertEqual(result['implementation_reference'],context['consumer_registry_view']['consumer_references'][role])
                self.assertEqual(value['shared_ancestry_verifier_reference'],context['bound_pair']['independent_reader_reference'])
                for key in metadata.FLAGS:self.assertIs(result[key],False)
        self.assertEqual(context,original)

    def test_each_metadata_field_missing_changed_and_strict_type_rejected(self):
        context=host_context()
        for role in metadata.ADAPTERS:
            baseline=metadata.expected_consumer_metadata(consumer_role=role,**context)
            for key in metadata.METADATA_KEYS:
                changed=deepcopy(baseline);del changed[key]
                with self.subTest(role=role,key=key,kind='missing'),self.assertRaises(ValueError):
                    metadata.inspect_consumer_metadata(changed,expected_role=role,**context)
                variants=(None,0,False,[],reference('other_'+key))if type(baseline[key])is dict else(None,0,False,[],role+'_other')
                for bad in variants:
                    changed=deepcopy(baseline);changed[key]=bad
                    with self.subTest(role=role,key=key,bad=bad),self.assertRaises(ValueError):
                        metadata.inspect_consumer_metadata(changed,expected_role=role,**context)
        for bad in (None,[],False,0,'metadata'):
            with self.subTest(wrapper=bad),self.assertRaises(ValueError):
                metadata.inspect_consumer_metadata(bad,expected_role='capture_publisher',**context)

    def test_unknown_roles_and_cross_consumer_roles_rejected(self):
        context=host_context()
        for role in (None,False,0,[],{},'capture','CONTINUATION_CAPTURE_PUBLISHER_V1'):
            with self.subTest(role=role),self.assertRaises(ValueError):
                metadata.expected_consumer_metadata(consumer_role=role,**context)
        value=metadata.expected_consumer_metadata(consumer_role='capture_publisher',**context)
        for role in metadata.ADAPTERS:
            if role=='capture_publisher':continue
            with self.subTest(role=role),self.assertRaises(ValueError):
                metadata.inspect_consumer_metadata(value,expected_role=role,**context)

    def test_pair_contract_registry_core_and_schema_host_associations(self):
        for group,key in [('consumer_registry_view','implementation_pair_binding_reference'),
                ('consumer_registry_view','ancestry_contract_reference')]:
            context=host_context();context[group][key]=reference('unbound_'+key)
            with self.subTest(group=group,key=key),self.assertRaises(ValueError):
                metadata.expected_consumer_metadata(consumer_role='capture_publisher',**context)
        for group in ('bound_pair','consumer_registry_view'):
            for key in ('schema','family','protocol'):
                context=host_context();context[group][key]='OTHER'
                with self.subTest(group=group,key=key),self.assertRaises(ValueError):
                    metadata.expected_consumer_metadata(consumer_role='capture_publisher',**context)
        context=host_context();context['consumer_registry_core_reference']=reference('wrong_consumer_core')
        with self.assertRaises(ValueError):metadata.expected_consumer_metadata(consumer_role='capture_publisher',**context)
        for role in consumer_kernel.CONSUMER_ROLES:
            context=host_context();del context['consumer_registry_view']['consumer_references'][role]
            with self.subTest(missing_role=role),self.assertRaises(ValueError):
                metadata.expected_consumer_metadata(consumer_role='capture_publisher',**context)
        context=host_context();context['consumer_registry_view']['consumer_references']['extra']=reference('extra')
        with self.assertRaises(ValueError):metadata.expected_consumer_metadata(consumer_role='capture_publisher',**context)

    def test_producer_public_inputs_preserve_both_business_role_keys_and_values(self):
        expected_roles={
            'capture_publisher':{'capture_core','parent_view','legacy_view','compact_helpers','scoped','base'},
            'observation_writer':{'payload_core','parent_view','compact_helpers','capture_checker','csv_reader'},
            'gap_publisher':{'gap_core','parent_view','legacy_view','compact_helpers','prefix_core','scoped','base','capture_checker'}}
        self.assertEqual({key:set(value)for key,value in metadata.REGISTERED_DEPENDENCY_ROLES.items()},expected_roles)
        for role,roles in expected_roles.items():
            value,deps,context=public_inputs(role);original=deepcopy(value)
            result=metadata.inspect_producer_input_references(value,consumer_role=role,registered_dependency_references=deps,**context)
            self.assertEqual(value['dependencies'],deps);self.assertEqual(result['registration_dependency_references'],deps)
            self.assertEqual(set(value['dependencies']),roles);self.assertEqual(value,original)
            for key in deps:
                changed=deepcopy(value)
                changed['dependencies'][key]=context['consumer_registry_view']['consumer_references']['capture_independent_reader']
                with self.subTest(role=role,key=key),self.assertRaises(ValueError):
                    metadata.inspect_producer_input_references(changed,consumer_role=role,registered_dependency_references=deps,**context)
            changed=deepcopy(value);changed['registration_dependency_references'][next(iter(deps))]=reference('changed_algorithm')
            with self.assertRaises(ValueError):metadata.inspect_producer_input_references(changed,consumer_role=role,registered_dependency_references=deps,**context)
            changed=deepcopy(value);changed['runtime']=reference('unbound_runtime')
            with self.assertRaises(ValueError):metadata.inspect_producer_input_references(changed,consumer_role=role,registered_dependency_references=deps,**context)

    def test_public_input_missing_refs_half_roles_and_dependency_type_rejected(self):
        for role in metadata.REGISTERED_DEPENDENCY_ROLES:
            value,deps,context=public_inputs(role)
            extensions=metadata.continuation_input_references(registered_dependency_references=deps,consumer_role=role,**context)
            self.assertEqual(set(extensions),{'registration_dependency_references','implementation_pair_binding','consumer_role_registry',
                'ancestry_contract','shared_ancestry_verifier','consumer_registry_core','consumer_metadata_contract'})
            for key in extensions:
                changed=deepcopy(value);del changed[key]
                with self.subTest(role=role,key=key),self.assertRaises(ValueError):
                    metadata.inspect_producer_input_references(changed,consumer_role=role,registered_dependency_references=deps,**context)
            for key in deps:
                changed=deepcopy(deps);del changed[key]
                with self.subTest(role=role,missing=key),self.assertRaises(ValueError):
                    metadata.continuation_input_references(registered_dependency_references=changed,consumer_role=role,**context)
            changed=deepcopy(deps);changed['extra_role']=reference('extra_algorithm')
            with self.assertRaises(ValueError):metadata.continuation_input_references(registered_dependency_references=changed,consumer_role=role,**context)
            for bad in (None,[],False,0):
                with self.subTest(role=role,deps=bad),self.assertRaises(ValueError):
                    metadata.continuation_input_references(registered_dependency_references=bad,consumer_role=role,**context)
        for role in metadata.PRODUCER_FOR_READER:
            with self.subTest(reader_not_producer=role),self.assertRaises(ValueError):
                metadata.continuation_input_references(registered_dependency_references={},consumer_role=role,**host_context())

    def test_producer_role_types_and_all_public_helpers_are_no_io(self):
        context=host_context()
        for bad in (None,False,0,[],{},'unknown'):
            with self.subTest(role=bad),self.assertRaises(ValueError):
                metadata.continuation_input_references(registered_dependency_references={},consumer_role=bad,**context)
        cases=[(role,*public_inputs(role))for role in metadata.REGISTERED_DEPENDENCY_ROLES]
        with patch('builtins.open',side_effect=AssertionError('No metadata producer IO')), \
                patch('pathlib.Path.read_bytes',side_effect=AssertionError('No source IO')), \
                patch('pathlib.Path.write_bytes',side_effect=AssertionError('No output IO')):
            for role,value,deps,host in cases:
                extensions=metadata.continuation_input_references(registered_dependency_references=deps,consumer_role=role,**host)
                self.assertEqual(metadata.inspect_producer_input_references(value,consumer_role=role,
                    registered_dependency_references=deps,**host),extensions)

    def test_five_file_observation_namespace_distinct_reader_start_and_business_adapter(self):
        self.assertEqual(metadata.OBSERVATION_READER_START_SCHEMA,'PROSPECTIVE_OBSERVATION_CONTINUATION_READER_STARTED_V1')
        self.assertEqual(metadata.OBSERVATION_BUSINESS_ADAPTER,'REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V5')
        result=metadata.inspect_consumer_metadata(metadata.expected_consumer_metadata(consumer_role='observation_independent_reader',**host_context()),
            expected_role='observation_independent_reader',**host_context())
        self.assertEqual(set(result['namespace_files']),{'started.json','observation_payload.json','receipt.json','reader_started.json','independent_readback.json'})
        self.assertEqual(len(result['namespace_files']),5)
        self.assertEqual(set(metadata.NAMESPACE_FILES['observation_writer']),{'started.json','observation_payload.json','receipt.json'})
        self.assertNotEqual('reader_started.json','started.json')
        self.assertEqual(len(metadata.NAMESPACE_FILES['capture_publisher']),6)
        self.assertEqual(len(metadata.NAMESPACE_FILES['gap_publisher']),7)
        self.assertEqual(metadata.PRODUCER_FOR_READER,{'capture_independent_reader':'capture_publisher',
            'observation_independent_reader':'observation_writer','gap_independent_reader':'gap_publisher'})

    def test_returned_metadata_views_and_extensions_are_deeply_detached(self):
        context=host_context();before=deepcopy(context)
        value=metadata.expected_consumer_metadata(consumer_role='capture_publisher',**context)
        report=metadata.inspect_consumer_metadata(value,expected_role='capture_publisher',**context)
        value['implementation_pair_binding_reference']['path']='changed'
        report['implementation_reference']['path']='changed'
        report['namespace_files'].append('extra.json');report['metadata']['consumer_role_registry_reference'].clear()
        self.assertEqual(context,before)
        deps=dependencies('observation_writer');deps_before=deepcopy(deps)
        extensions=metadata.continuation_input_references(registered_dependency_references=deps,consumer_role='observation_writer',**context)
        extensions['registration_dependency_references']['capture_checker']['path']='changed'
        extensions['consumer_role_registry'].clear()
        self.assertEqual(deps,deps_before);self.assertEqual(context,before)
        inputs,original_deps,context=public_inputs('gap_publisher')
        before=deepcopy(inputs)
        inspected=metadata.inspect_producer_input_references(inputs,consumer_role='gap_publisher',registered_dependency_references=original_deps,**context)
        inspected['registration_dependency_references'].clear()
        self.assertEqual(inputs,before)

    def test_extra_wrapper_fields_are_not_a_full_wrapper_authentication_claim(self):
        context=host_context();value=metadata.expected_consumer_metadata(consumer_role='capture_publisher',**context)
        value.update(schema='UNVERIFIED_WRAPPER_SCHEMA',unrecognized_reference=reference('not_authorized_for_io'))
        report=metadata.inspect_consumer_metadata(value,expected_role='capture_publisher',**context)
        self.assertIs(report['full_wrapper_verified'],False);self.assertIs(report['source_claims_select_io'],False)
        self.assertNotIn('unrecognized_reference',report['metadata'])


if __name__=='__main__':unittest.main()
