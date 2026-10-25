from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import subprocess
import unittest
from test_run_registered_paper_automation import setup as base_setup
import json
from hashlib import sha256
from scripts import preflight_registered_paper_task_cutover as cutover

def setup(folder,existing=True):
    args,now,store=base_setup(folder,existing);root=Path(folder)
    def save(name,value):
        (root/name).write_text(json.dumps(value));return {'path':name,'sha256':sha256((root/name).read_bytes()).hexdigest()}
    descriptor=json.loads((root/'automation.json').read_bytes())
    validated=cutover.automation.runtime.load_bundle(root=root,registration_directory='registration',expected_request_sha256=descriptor['request_sha256'],now=now)
    refs=validated['request']['refs'];pins={}
    paths={name:Path(where()) for name,where in cutover.automation.publisher.MODULES.items()}
    paths.update({name:Path(cutover.__file__).resolve().parents[1]/name for name in cutover.automation.publisher.COMPILE_SOURCES})
    for name,source in paths.items():
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes());pins[name]=sha256(target.read_bytes()).hexdigest()
    domain=save('domain.json',{'members':['A']});domain_pins={domain['path']:domain['sha256']}
    plan=save('plan.json',{'domain_path':domain['path'],'domain_source_hashes':domain_pins})
    settings=save('settings.json',{'plan_path':plan['path'],'plan_sha256':plan['sha256'],'schedule_path':refs['calendar']['path'],'fixed_source_hashes':{refs['calendar']['path']:refs['calendar']['sha256']}})
    first=save('first.json',{'daily_config':refs['daily']['path'],'daily_sha256':refs['daily']['sha256'],'settings_path':settings['path'],'settings_sha256':settings['sha256']})
    rolling=save('rolling.json',{'bootstrap':refs['bootstrap'],'first_coordinator':first})
    descriptor['publication_policy']=save('policy.json',dict(schema='REGISTERED_PAPER_MONTHLY_PUBLICATION_POLICY_V1',authorization='COMPLETED_PAPER_BIND_ONLY',request_sha256=descriptor['request_sha256'],registration_directory='registration',source_hashes=pins,rolling=rolling,domain=domain,domain_source_hashes=domain_pins))
    args['expected_descriptor_sha256']=save('automation.json',descriptor)['sha256']
    return args,now,store


class CutoverTests(unittest.TestCase):
    def test_draft_policy_and_compiler_drift_rejected(self):
        with TemporaryDirectory() as folder:
            args,_,_=setup(folder);root=Path(folder)
            path=root/cutover.automation.publisher.COMPILE_SOURCES[0];path.write_text('changed')
            with self.assertRaisesRegex(ValueError,'MONTHLY_SOURCE_CHANGED'):cutover.preflight(**args)
        with TemporaryDirectory() as folder:
            args,_,_=setup(folder);root=Path(folder)
            policy=json.loads((root/'policy.json').read_bytes());policy['authorization']='DRAFT';(root/'policy.json').write_text(json.dumps(policy))
            descriptor=json.loads((root/'automation.json').read_bytes());descriptor['publication_policy']['sha256']=sha256((root/'policy.json').read_bytes()).hexdigest();(root/'automation.json').write_text(json.dumps(descriptor));args['expected_descriptor_sha256']=sha256((root/'automation.json').read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'MONTHLY_PUBLICATION_AUTHORITY_REQUIRED'):cutover.preflight(**args)
    def test_absent_and_real_registered_store_are_read_only(self):
        for existing in (False,True):
            with self.subTest(existing=existing),TemporaryDirectory() as folder:
                args,_,store=setup(folder,existing)
                before={str(p):p.read_bytes() for p in Path(folder).rglob('*') if p.is_file()}
                result=cutover.preflight(**args)
                self.assertEqual(result['database_state'],'REGISTERED_START_VERIFIED' if existing else 'ABSENT')
                self.assertEqual(before,{str(p):p.read_bytes() for p in Path(folder).rglob('*') if p.is_file()})

    def test_lock_wrong_hash_and_missing_start_rejected(self):
        with TemporaryDirectory() as folder:
            args,_,_=setup(folder)
            with self.assertRaisesRegex(ValueError,'DESCRIPTOR_CHANGED'):cutover.preflight(**dict(args,expected_descriptor_sha256='a'*64))
            lock=Path(folder)/cutover.automation.registrar.LOCK;lock.parent.mkdir(parents=True,exist_ok=True);lock.write_text('owner')
            with self.assertRaisesRegex(ValueError,'SHARED_LOCK'):cutover.preflight(**args)
            self.assertEqual(cutover.preflight(**args,owned_lock_token='owner')['status'],'CUTOVER_ADMISSION_VERIFIED')
            with self.assertRaisesRegex(ValueError,'OWNERSHIP'):cutover.preflight(**args,owned_lock_token='other')
            lock.unlink();(Path(folder)/'registration/runtime/start_complete.json').unlink()
            with self.assertRaisesRegex(ValueError,'EXISTING_DATABASE_WITHOUT_REGISTERED_START'):cutover.preflight(**args)

    def test_powershell_parses_and_mutations_are_only_after_apply_gate(self):
        path=Path(__file__).resolve().parents[1]/'scripts/switch_registered_paper_tasks.ps1'
        script=path.read_text()
        command="$e=$null; $t=$null; [System.Management.Automation.Language.Parser]::ParseFile('"+str(path).replace("'","''")+"',[ref]$t,[ref]$e) | Out-Null; if ($e.Count) { $e | Out-String | Write-Output; exit 1 }"
        checked=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True)
        self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
        gate=script.index('if (-not $Apply)')
        self.assertGreater(script.index('Set-ScheduledTask -TaskName'),gate)
        self.assertGreater(script.index('Register-ScheduledTask -TaskName'),gate)
        self.assertNotIn('UsRatchet-RealMonthly-Update',script)
        self.assertNotIn('automation.toml',script)


if __name__=='__main__':unittest.main()
