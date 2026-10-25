from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
from datetime import timedelta
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_continuous32_target_decision import decide_target, REQUIRED_PINS, PROFILE_ID, VERSION
from data.strategy_daily_signal_verifier import ROOT, POLICY
from data.strategy_daily_composition_v3 import DailyCompositionV3
from data.strategy_profiled_daily_packet_admission import ProfiledCurrentSessionDailyReader
import test_daily_composition_v3 as fixtures
from data.strategy_account_market_capture import StrategyAccountMarketCapture

class ProfiledPacketTests(unittest.TestCase):
    def setup_case(self,directory):
        c=fixtures.CompositionTests().setup_case(directory)
        root=Path(directory)
        args=c.provider.selection(c.state)
        for name in REQUIRED_PINS:
            raw=(ROOT/name).read_bytes()
            args['source_package']['files'][name]=raw
            args['source_package']['source_hashes'][name]=sha256(raw).hexdigest()
        decision=decide_target(state=c.state,now=c.clock[0].isoformat(),maximum_mark_age_seconds=900,**args)
        c.target['payload'].update(schema='REAL_STRATEGY_MONTHLY_TARGET_V1',decision=decision,
            target_quantities=decision['payload']['target_quantities'])
        c.target['target_id']=sha256(canonical(c.target['payload'])).hexdigest()
        release=json.loads((root/'release.json').read_bytes())
        release.update(selector_profile=PROFILE_ID,selection_method=VERSION,continuous_iterations=32)
        release_raw=canonical(release);(root/'release.json').write_bytes(release_raw)
        receipt=json.loads((root/'parent.json').read_bytes())
        inputs=json.loads((root/'normalized.json').read_bytes())
        inputs['base_target']['quantities']=decision['payload']['target_quantities']
        (root/'normalized.json').write_bytes(canonical(inputs))
        receipt.update(target_id=c.target['target_id'],release_sha256=sha256(release_raw).hexdigest())
        receipt['source_sha256']['normalized.json']=sha256(canonical(inputs)).hexdigest()
        def save(name,raw):
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            return dict(path=name,sha256=sha256(raw).hexdigest())
        parent=save('parent.json',canonical(receipt))
        security=dict(ticker='BBB',security_id='B',currency='USD',exchangeName='NMS',instrumentType='EQUITY')
        identity=save('identity.json',canonical(dict(schema='SERVER_CAPTURE_IDENTITY_V1',review_status='REVIEWED',security=security,fixture_only=True)))
        calendar=dict(path='calendar.json',sha256=sha256((root/'calendar.json').read_bytes()).hexdigest())
        capture=save('capture-config.json',canonical(dict(identity_review=identity,security=security,calendar=calendar)))
        config=save('pipeline.json',canonical(dict(schema='SERVER_DAILY_SOURCE_PIPELINE_V1',source_pins=[],capture_configuration=capture,parent_reference=parent,runs_root='runs',account_id=c.state['account_id'])))
        manifest={}
        for name,digest in receipt['source_sha256'].items():
            manifest[name]=save('runs/2026-11-02/files/'+digest+'.bin',(root/name).read_bytes())
        rr=save('runs/2026-11-02/receipt.json',canonical(receipt))
        mr=save('runs/2026-11-02/source-paths.json',canonical(manifest))
        save('runs/2026-11-02/terminal.json',canonical(dict(status='DAILY_CONDITIONAL_PACKET_SAVED',session='2026-11-02',configuration_sha256=config['sha256'],receipt_reference=rr,manifest_reference=mr,finished_at=receipt['available_at'])))
        reader=ProfiledCurrentSessionDailyReader(root=root,configuration_path=config['path'],configuration_sha256=config['sha256'],archive_root=root/'packet-archive',release_path='release.json',trusted_release_sha256=sha256(release_raw).hexdigest())
        c.service=DailyCompositionV3(monthly_service=c.monthly,evidence_reader=reader,execution_provider=c.provider.execution,clock=lambda:c.clock[0],policy_execution_enabled=True,policy_id=POLICY,fee_bps='10')
        return c

    def test_approved_fixture_actual_provider(self):
        with TemporaryDirectory() as directory:
            c=self.setup_case(directory)
            result=c.service.preview(expected_revision=c.state['revision'],target_id=c.target['target_id'])
            self.assertEqual(result['status'],'READY',result)
            self.assertTrue(result['evidence_archive'])
            self.assertEqual(result['new_orders'][0]['side'],'SELL')

    def test_future_receipt_and_wrong_selector_stop_before_quotes(self):
        for mode in ('future','selector'):
            with self.subTest(mode=mode),TemporaryDirectory() as directory:
                c=self.setup_case(directory)
                if mode=='future':
                    c.clock[0]=datetime.fromisoformat('2026-11-02T14:00:00+00:00')
                else:
                    binding=c.target['payload']['decision']['payload']['input_binding']
                    binding['selector_profile']='OLD_V2'
                    decision=c.target['payload']['decision']
                    decision['payload']['input_id']=sha256(canonical(binding)).hexdigest()
                    decision['decision_id']=sha256(canonical(decision['payload'])).hexdigest()
                    c.target['target_id']=sha256(canonical(c.target['payload'])).hexdigest()
                def forbidden(*args,**kwargs):raise AssertionError('must not capture execution quotes')
                c.provider.market.capture=forbidden
                with self.assertRaisesRegex(ValueError,'PACKET_AVAILABILITY_CHANGED' if mode=='future'
                                            else 'DAILY_TARGET_SELECTOR_PROFILE_MISMATCH'):
                    c.service.preview(expected_revision=c.state['revision'],target_id=c.target['target_id'])
                self.assertFalse((Path(directory)/'packet-archive').exists())

    def test_buy_hold_and_missing_packet_with_real_account_rebinding(self):
        for mode in ('BUY','HOLD','WAIT'):
            with self.subTest(mode=mode),TemporaryDirectory() as directory:
                c=self.setup_case(directory)
                half=c.target['payload']['target_quantities']['B']//2
                if mode in ('BUY','HOLD'):
                    quantity=14 if mode=='BUY' else 14-half
                    identity=c.state['events'][0]['payload']['identity_evidence']
                    c.store.append(dict(event_id='sell-after-target',kind='DIRECT_FILL',security_id='B',side='SELL',quantity=quantity,price='10',fees='0',executed_at=c.clock[0].isoformat(),identity_evidence=identity),expected_revision=c.state['revision'])
                    c.store.append(dict(event_id='cash-after-fill',kind='CASH_CONFIRM',amount='1000' if mode=='BUY' else '0',cash_basis='TOTAL_UNINVESTED'),expected_revision=c.store.read()['revision'])
                    c.state=c.store.read()
                    if mode=='BUY':
                        class Identity:
                            def __call__(self,ticker):
                                return dict(ticker=ticker,security_id='B',source_references=['identity-only'],
                                    source_hashes={'identity-only':sha256(b'id').hexdigest()})
                            def _read(self,*args):return b'id'
                        def raw(ticker):
                            opening=int(datetime.fromisoformat('2026-11-02T14:30:00+00:00').timestamp())
                            last=opening+1800
                            return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,
                                currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',
                                dataGranularity='1m',regularMarketPrice=10,regularMarketTime=last,
                                currentTradingPeriod=dict(regular=dict(start=opening,end=opening+23400))),
                                timestamp=list(range(opening,last,60)),indicators=dict(quote=[dict(
                                    open=[10]*30,high=[11]*30,low=[9]*30,close=[10]*30,volume=[10]*30)]))])))
                        c.provider.market=StrategyAccountMarketCapture(identity_resolver=Identity(),
                            fetch=raw,clock=lambda:c.clock[0],max_mark_age=120)
                else:
                    (Path(directory)/'runs/2026-11-02/terminal.json').rename(Path(directory)/'saved-terminal.json')
                before=c.store.path.read_bytes()
                result=c.service.preview(expected_revision=c.state['revision'],target_id=c.target['target_id'])
                self.assertEqual(result['status'],'READY' if mode=='BUY' else mode,result)
                self.assertEqual(c.store.path.read_bytes(),before)
                if mode=='BUY':self.assertEqual(result['new_orders'][0]['side'],'BUY')
                else:self.assertEqual(result['new_orders'],[])

if __name__=='__main__':unittest.main()
