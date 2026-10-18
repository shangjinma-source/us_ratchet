"""Independent adversarial pure registration checks, no source or output IO."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_observation_runtime_registration_research_v1 as module
import test_ndx_observation_runtime_registration_research_v1 as author


def all_references(args):
    return [args['registration_reference'],args['runtime_reference'],
        *args['dependency_references'].values(),*args['registration']['parent'].values(),
        *args['registration']['capture'].values()]


class IndependentObservationRegistrationTests(unittest.TestCase):
    def test_case_separator_alias_conflicts_across_input_roles(self):
        original=author.fixture()
        for index,item in enumerate(all_references(original)[:-1]):
            a=author.fixture()
            a['registration']['capture']['reader_reference']=dict(path=item['path'].upper().replace('/','\\'),sha256='f'*64)
            with self.subTest(index=index),self.assertRaisesRegex(ValueError,'aliases'):module.prepare_observation_runtime(**a)
        a=author.fixture();a['registration']['runtime_reference']['path']=a['runtime_reference']['path'].upper()
        with self.assertRaisesRegex(ValueError,'Host runtime'):module.prepare_observation_runtime(**a)

    def test_exact_reference_structure_rejects_embedded_authority_or_pointer(self):
        for index in range(len(all_references(author.fixture()))):
            for key,value in (('json_pointer','/history'),('source_authenticity_verified',True),('bytes_verified',False)):
                a=author.fixture();all_references(a)[index][key]=value
                with self.subTest(index=index,key=key),self.assertRaises(ValueError):module.prepare_observation_runtime(**a)

    def test_every_input_role_cannot_be_below_output_namespace(self):
        # Host bindings are kept mutually equal, so rejection must be path isolation.
        for index in range(len(all_references(author.fixture()))):
            a=author.fixture();refs=all_references(a);refs[index]['path']=a['registration']['output_directory']+'/nested/input.json'
            a['registration']['runtime_reference']=deepcopy(a['runtime_reference'])
            a['registration']['dependency_references']=deepcopy(a['dependency_references'])
            with self.subTest(index=index),self.assertRaisesRegex(ValueError,'Output aliases'):module.prepare_observation_runtime(**a)

    def test_detached_plan_source_union_and_no_filesystem_or_clock(self):
        a=author.fixture();before=deepcopy(a)
        with (patch.object(Path,'read_bytes',side_effect=AssertionError('read')),
              patch.object(Path,'open',side_effect=AssertionError('open')),
              patch.object(Path,'stat',side_effect=AssertionError('stat')),
              patch.object(Path,'mkdir',side_effect=AssertionError('mkdir'))):
            plan=module.prepare_observation_runtime(**a)
        self.assertEqual(a,before)
        self.assertEqual(plan['source_reference_claims'],{r['path']:r['sha256'] for r in all_references(a)})
        for role in ('parent','capture','dependency_references'):
            next(iter(plan[role].values()))['sha256']='f'*64
        plan['runtime_reference']['path']='E:/mutated.py';plan['registration_reference'].clear();plan['source_reference_claims'].clear()
        self.assertEqual(a,before)

    def test_windows_path_and_nonliteral_schema_attack_surface(self):
        for suffix in ('safe/../escaped','safe/./nested','safe:stream','safe.','safe ','safe\x00','COM1.txt','lpt9.py','new?name','évalid',
                       'a'*121,'Uppercase'):
            a=author.fixture();a['registration']['output_directory']=a['research_root']+'/'+suffix
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):module.prepare_observation_runtime(**a)
        for value in (None,{},[],True,1,'PROSPECTIVE_OBSERVATION_RUNTIME_REGISTRATION_V2'):
            a=author.fixture();a['registration']['schema']=value
            with self.subTest(value=value),self.assertRaises(ValueError):module.prepare_observation_runtime(**a)


if __name__=='__main__':unittest.main()
