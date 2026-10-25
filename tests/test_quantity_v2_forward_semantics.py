from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts import build_quantity_v2_forward_semantics as m


class SemanticManifestTests(unittest.TestCase):
    def repin_source(self,root,request,path):
        digest=sha256((root/path).read_bytes()).hexdigest()
        for name in ('descriptor.json','dependencies.json'):
            value=json.loads((root/name).read_bytes());value['source_hashes'][path]=digest
            (root/name).write_text(json.dumps(value))
        value=json.loads((root/'bootstrap.json').read_bytes())
        value['descriptor']['sha256']=sha256((root/'descriptor.json').read_bytes()).hexdigest()
        (root/'bootstrap.json').write_text(json.dumps(value))
        for key in ('bootstrap','dependencies'):
            request[key]['sha256']=sha256((root/request[key]['path']).read_bytes()).hexdigest()

    def fixture(self,root):
        def save(name,value):
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(value if isinstance(value,str) else json.dumps(value))
            return dict(path=name,sha256=sha256(path.read_bytes()).hexdigest())
        code={m.SELECTOR:"VERSION='ACTUAL_METHOD'",m.TRAINING:'def f(days):\n assert len(days)==253\n return range(0,252,21),range(12),days[21::21]',
              m.SELL:'sell=Fraction(-(-last*100//1),100)\nif delta<0: orders.append(delta)',
              m.CADENCE:"ny=clock.astimezone(ZoneInfo('America/New_York'))\nif (ny.hour,ny.minute)!=(10,0): return_value='SKIP'",
              m.CAPITAL:"data['search_arguments']['entered_cash']=str(ledger['cash']+held_value)"}
        pins={name:save(name,text)['sha256'] for name,text in code.items()}
        data=dict(search_arguments=dict(max_objective_evaluations=8192,fixed_seed='fixed',fee_bps='0',minimum_cash_buffer='0',
            decision_date='2026-10-14',price_basis='CONDITIONAL',training_scenarios=[{'A':'1'}]*12,
            scenario_dates=['d']*12,prices={'A':'10'},metadata={'A':{'ticker':'A'}}))
        inp=save('input.json',data);pins[inp['path']]=inp['sha256']
        descriptor=save('descriptor.json',dict(input_path=inp['path'],source_hashes=pins))
        fees=save('fees.json',dict(fixed_per_order='0',notional_rate='0'))
        bootstrap=dict(descriptor=descriptor,fees=fees,initial_cash='20000',simulation_id='test',model='STRICT_CROSS_FULL_FILL_AT_LIMIT',pullback=dict(policy={'minimum_discount':'1/200'}))
        domain=save('domain.json',dict(schema='EXPERIMENTAL_DERIVED_DOMAIN_V1',members=['A'],fixed_security_count=1,
            point_in_time_membership_verified=False,new_membership_observation=False,exclusions=[]))
        return dict(bootstrap=save('bootstrap.json',bootstrap),daily=save('daily.json',dict(simulation_id='test',pullback=bootstrap['pullback'])),
            dependencies=save('dependencies.json',dict(source_hashes=pins)),monthly_plan=save('plan.json',dict(domain_path=domain['path'],domain_source_hashes={domain['path']:domain['sha256']})))

    def test_values_extracted_not_hardcoded_and_no_writes(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);request=self.fixture(root)
            before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result=m.build(root=root,request=request)
            self.assertEqual(result['rules']['selection_method']['value'],'ACTUAL_METHOD')
            self.assertEqual(result['rules']['domain']['value']['fixed_security_count'],1)
            self.assertEqual(result['rules']['training_window_and_partition']['value']['calendar_length_constraints'][0]['value'],253)
            self.assertEqual(result['rules']['daily_clock_gate']['status'],'EXTRACTED_EXECUTABLE_SYNTAX')
            self.assertFalse(result['registered']);self.assertFalse(result['protocol_equivalence_certified'])
            self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_changed_code_refused_even_if_not_executed(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);request=self.fixture(root)
            (root/m.SELECTOR).write_text("VERSION='OTHER'")
            with self.assertRaisesRegex(ValueError,'SEMANTIC_SOURCE_CHANGED'):m.build(root=root,request=request)

    def test_missing_domain_never_invents_fixed98(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);request=self.fixture(root);request.pop('monthly_plan')
            self.assertEqual(m.build(root=root,request=request)['rules']['domain']['status'],'UNRESOLVED')

    def test_additional_approved_pins_cannot_override(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);request=self.fixture(root)
            (root/'extra.json').write_text(json.dumps({'source_pins':{m.SELECTOR:'a'*64}}))
            request['additional_pin_manifests']=[dict(path='extra.json',
                sha256=sha256((root/'extra.json').read_bytes()).hexdigest(),field='source_pins')]
            with self.assertRaisesRegex(ValueError,'REFERENCE_PIN_CONFLICT'):m.build(root=root,request=request)

    def test_wrong_domain_does_not_claim_matching(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);request=self.fixture(root)
            domain=json.loads((root/'domain.json').read_bytes());domain['members']=['B']
            (root/'domain.json').write_text(json.dumps(domain))
            plan=json.loads((root/'plan.json').read_bytes());plan['domain_source_hashes']['domain.json']=sha256((root/'domain.json').read_bytes()).hexdigest()
            (root/'plan.json').write_text(json.dumps(plan));request['monthly_plan']['sha256']=sha256((root/'plan.json').read_bytes()).hexdigest()
            self.assertEqual(m.build(root=root,request=request)['rules']['domain']['status'],'UNRESOLVED')

    def test_reassigned_version_is_ambiguous(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);request=self.fixture(root)
            (root/m.SELECTOR).write_text("VERSION='OLD'\nVERSION='NEW'\n")
            self.repin_source(root,request,m.SELECTOR)
            field=m.build(root=root,request=request)['rules']['selection_method']
            self.assertEqual(field['status'],'UNRESOLVED');self.assertEqual(len(field['candidates']),2)

    def test_two_clock_guards_are_ambiguous(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);request=self.fixture(root)
            with (root/m.CADENCE).open('a') as f:f.write("\nif (ny.hour,ny.minute)!=(11,0): other='SKIP'\n")
            self.repin_source(root,request,m.CADENCE)
            field=m.build(root=root,request=request)['rules']['daily_clock_gate']
            self.assertEqual(field['status'],'UNRESOLVED');self.assertEqual(len(field['candidates']),2)

    def test_alignment_lists_all_missing_and_different_fields(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);request=self.fixture(root)
            bootstrap=json.loads((root/'bootstrap.json').read_bytes())
            bootstrap.update(root=str(root),database_path=str(root/'one.sqlite3'),account_id='account',schedule={'path':'cal','sha256':'a'*64})
            (root/'bootstrap.json').write_text(json.dumps(bootstrap))
            request['bootstrap']['sha256']=sha256((root/'bootstrap.json').read_bytes()).hexdigest()
            daily=json.loads((root/'daily.json').read_bytes())
            daily.update(root='other',database_path='other-db',fees_path='different',fees_sha256='b'*64,
                         schedule_path='different',schedule_sha256='b'*64)
            (root/'daily.json').write_text(json.dumps(daily));request['daily']['sha256']=sha256((root/'daily.json').read_bytes()).hexdigest()
            field=m.build(root=root,request=request)['rules']['bootstrap_daily_alignment']
            self.assertEqual(field['status'],'UNRESOLVED')
            self.assertEqual({x['field'] for x in field['differences']},{'root','database_path','account_id','fees','schedule'})

    def test_price_metadata_identity_mismatch_and_duplicate_ticker_rejected(self):
        for mode in ('different_keys','duplicate_ticker'):
            with self.subTest(mode=mode),TemporaryDirectory() as directory:
                root=Path(directory);request=self.fixture(root)
                value=json.loads((root/'input.json').read_bytes());args=value['search_arguments']
                if mode=='different_keys':args['prices']={'B':'10'}
                else:
                    args['prices']['B']='10';args['metadata']['B']={'ticker':'A'}
                (root/'input.json').write_text(json.dumps(value));self.repin_source(root,request,'input.json')
                self.assertEqual(m.build(root=root,request=request)['rules']['domain']['status'],'UNRESOLVED')


if __name__=='__main__':unittest.main()
