"""Independent synthetic source/lifecycle checks; never real cash preparation."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_single_replacement_preparation_20261003 as m
from test_ndx_single_replacement_preparation_20261003 import physical


def rewrite(bound, refs, role, document):
    path=Path(refs[role]['path']);data=m.enc(document);path.write_bytes(data)
    bound[role]=(str(path),m.sha(data));refs[role]={'path':str(path),'sha256':m.sha(data)}


class Tests(unittest.TestCase):
    def test_interleaved_original64_locations_and_direct_sources_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bound,refs=physical(root)
            source=json.loads(Path(refs['inputs']['path']).read_bytes())
            main=source['rows'][:40];controls=source['rows'][40:]
            source['rows']=[item for i,row in enumerate(main) for item in ([controls[i],row] if i<24 else [row])]
            rewrite(bound,refs,'inputs',source)
            publication=json.loads(Path(refs['input_publication']['path']).read_bytes());publication['input_reference']=refs['inputs'];rewrite(bound,refs,'input_publication',publication)
            policy=json.loads(Path(refs['policy']['path']).read_bytes());policy['original_inputs_reference']=refs['inputs']
            policy['original_row_references']=[dict(scenario_id=row['scenario_id'],reference={**refs['inputs'],'json_pointer':f'/rows/{i}'}) for i,row in enumerate(source['rows']) if row['branch_role']=='MAIN_LANE']
            rewrite(bound,refs,'policy',policy);policy_bytes=Path(refs['policy']['path']).read_bytes()
            original_read=Path.read_bytes;forbidden=m.ROOT/m.ACCOUNT_CLAIM[0]
            def checked_read(path):
                self.assertNotEqual(path,forbidden,'Original account must not be reread')
                return original_read(path)
            with patch.multiple(m,BOUND=bound,OUTPUT=root/'out'),patch.object(m,'resource'),patch.object(Path,'read_bytes',checked_read):
                output=m.run(execute=True)
            saved=json.loads(Path(output['path']).read_bytes());body=saved['preparation']['document']
            self.assertEqual([r['identity']['input_reference']['json_pointer'] for r in body['cases']],[r['reference']['json_pointer'] for r in policy['original_row_references']])
            self.assertEqual(len(saved['input_references']),12);self.assertEqual(len(saved['declared_parent_sources']),5)
            self.assertNotIn(str(forbidden),saved['source_hashes']);self.assertIn(str(forbidden),saved['declared_parent_sources'])
            self.assertFalse(saved['full_transitive_source_closure_reverified']);self.assertFalse(saved['old_holdings_reconstructed'])
            self.assertEqual(Path(refs['policy']['path']).read_bytes(),policy_bytes)
            self.assertNotIn('action_contract_reference',policy['action_policy'])
            self.assertEqual(body['action_contract']['action_contract_reference'],refs['policy'])

    def test_late_parent_intruder_and_late_output_drift_retain_raw_no_retry(self):
        for mode in ('parent','output'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);bound,refs=physical(root)
                with patch.multiple(m,BOUND=bound,OUTPUT=root/'out'),patch.object(m,'resource'):
                    context=m.load_inputs();core=context[-1];real=core.prepare_single_replacement_domain
                    def wrapped(*args):
                        result=real(*args)
                        if mode=='parent':(Path(refs['scenarios']['path']).parent/'failure.json').write_bytes(b'failure marker')
                        return result
                    core.prepare_single_replacement_domain=wrapped
                    real_save=m.save
                    def saved(name,value,emergency=False):
                        ref=real_save(name,value,emergency)
                        if mode=='output' and name=='publication.json':(m.OUTPUT/'started.json').write_bytes(b'changed after publication')
                        return ref
                    with patch.object(m,'load_inputs',return_value=context),patch.object(m,'save',side_effect=saved):
                        with self.assertRaises(ValueError):m.run(execute=True)
                    raw=json.loads((m.OUTPUT/'raw_preparation.json').read_bytes());self.assertIs(raw['returned'],True)
                    self.assertEqual(raw['result']['document']['scenario_count'],40)
                    self.assertEqual(json.loads((m.OUTPUT/'failure.json').read_bytes())['status'],'FAILED_DO_NOT_RETRY_OR_CONSUME')
                    with self.assertRaisesRegex(ValueError,'retry'):m.run(execute=True)

    def test_declared_account_claim_not_authenticated_or_replaced_and_role_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            bound,refs=physical(Path(tmp))
            with patch.object(m,'BOUND',bound):
                documents,r,*_=m.load_inputs()
                for mode in ('claim','row','permission','policy_permission'):
                    d=deepcopy(documents)
                    if mode=='claim':
                        key=str(m.ROOT/m.ACCOUNT_CLAIM[0]);d['inputs']['source_hashes'][key]='f'*64;d['input_publication']['source_hashes'][key]='f'*64
                    elif mode=='row':d['inputs']['rows'][0]['scenario_reference']['json_pointer']='/rows/1'
                    elif mode=='permission':d['input_publication']['old_audit_rerun']=0
                    else:d['policy']['evaluation_authorized']=True
                    with self.subTest(mode=mode),self.assertRaises(ValueError):m.project(d,r)
            bound['core']=(bound['core'][0],None)
            with patch.object(m,'BOUND',bound),patch.object(Path,'read_bytes',side_effect=AssertionError('IO before anchor gate')):
                with self.assertRaisesRegex(ValueError,'Pending'):m.load_inputs()


if __name__=='__main__':unittest.main()
