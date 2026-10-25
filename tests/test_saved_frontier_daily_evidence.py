"""Complete synthetic saved-source fixture; no optimizer or live market request."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from core.strategy_account_store import StrategyAccountStore
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.saved_frontier_policy_archive import archive_saved_frontier_policy
from data.saved_frontier_daily_evidence import verify_saved_frontier_daily_evidence
from test_saved_monthly_frontier_proposal import native_fixture, sign


def digest(raw):
    return sha256(raw).hexdigest()


def joint_fixture(root, *, archive=True, fee='1', tie=False):
    """Real isolated ledger/risk databases and complete A/B/D/E source documents."""
    root = Path(root)
    root.mkdir(exist_ok=True)
    created = datetime.fromisoformat('2026-10-20T20:00:03+00:00')
    accounts = StrategyAccountStore(root/'account.sqlite3', clock=lambda: created)
    accounts.initialize('synthetic-account', operation_id='initialize')
    events = [dict(event_id='old-holding',kind='DIRECT_FILL',security_id='D',side='BUY',quantity=3,
                   price='50',fees='0',executed_at='2026-10-20T14:00:00+00:00'),
              dict(event_id='cash-before',kind='CASH_CONFIRM',amount='19850',cash_basis='TOTAL_UNINVESTED'),
              dict(event_id='open-existing',kind='ORDER_OPEN',order_id='old-open-E',security_id='E',
                   side='BUY',quantity=1,limit_price='20',fee_per_share='0'),
              dict(event_id='cash-current',kind='CASH_CONFIRM',amount='19850',cash_basis='TOTAL_UNINVESTED')]
    ledger_identity_source=canonical(dict(scope='synthetic ledger identity',securities=['D','E']))
    for event in events:
        if event['kind'] in {'DIRECT_FILL','ORDER_OPEN'}:
            sid=event['security_id']
            event['identity_evidence']=dict(security_id=sid,ticker=sid,
                source_references=['ledger-identity.json'],
                source_hashes={'ledger-identity.json':digest(ledger_identity_source)})
    for event in events:
        accounts.append(event, expected_revision=accounts.read()['revision'])
    state = accounts.read()
    target = native_fixture(fee=fee, tie=tie)
    binding = target['payload']['decision']['payload']['input_binding']
    binding.update(account_revision=state['revision'], holdings_revision=state['holdings_revision'],
        strategy_shares={'D':3}, holding_market_values={'D':'150'}, total_uninvested_cash='19850')
    binding['marks']['D'] = dict(deepcopy(binding['marks']['C']), security_id='D', ticker='D')
    binding['marks']['E'] = dict(deepcopy(binding['marks']['C']), security_id='E', ticker='E',price='20')
    binding['execution_context'].update(available_cash=state['available_cash'], reserved_cash=state['reserved_cash'],
        pending_orders=[deepcopy(state['orders']['old-open-E'])],
        cash_confirmation_revision=state['cash_confirmed_for_holdings_revision'],
        reserved_shares=deepcopy(state['reserved_shares']),sell_proceeds_available=False)
    binding['historical_search_arguments'].update(decision_date=binding['training_cutoff_date'],price_basis='UNADJUSTED_USD')
    source_files = {name:canonical(dict(synthetic_source=name)) for name in binding['source_hashes']}
    source_files[binding['documents']['training_manifest']] = canonical(dict(decision_date=binding['training_cutoff_date']))
    binding['source_hashes'] = {name:digest(raw) for name,raw in source_files.items()}
    for mark in binding['marks'].values():
        mark['source_hashes'] = {name:binding['source_hashes'][name] for name in mark['source_references']}
    target['payload']['runtime_pins'] = {}
    repository=Path(__file__).resolve().parents[1]
    for name in ('core/strategy_monthly_target_store.py','data/strategy_monthly_target_service.py'):
        source_files[name]=(repository/name).read_bytes()
        target['payload']['runtime_pins'][name]=digest(source_files[name])
    target['payload']['request']['expected_revision']=state['revision']
    sign(target)
    proposal = build_frontier_proposal(target=target)
    research_root=root/'archive'
    research_root.mkdir()
    if archive:
        archive_saved_frontier_policy(research_root=research_root,target=target,proposal=proposal,
                                      source_files=source_files,enabled=True)
    risk_path=root/'risk.sqlite3'
    risk=MonthlyPeakExitStore(risk_path)
    observations=[]
    for day,price in [('2026-10-20','100'),('2026-10-21','70')]:
        row=dict(decision_date='2026-10-20',session_date=day,closes={'A':price},unit_ids={'A':'unit-A'})
        row['evidence_sha256']=digest(json.dumps(row,sort_keys=True).encode())
        observations.append(row)
    risk.advance(account_id=state['account_id'],expected_previous_session=None,observations=observations,
                 baseline_targets={'A':100},target_month='2026-10')
    risk_state=risk.read(state['account_id'])
    days=['2026-10-20','2026-10-21','2026-10-22','2026-10-23']
    sessions=[dict(date=day,open=day+'T13:30:00+00:00',close=day+'T20:00:00+00:00') for day in days]
    current='2026-10-23T14:00:00+00:00'
    received='2026-10-23T13:00:00+00:00'
    reviewed='2026-10-23T13:01:00+00:00'
    needed=sorted({sid for sid,q in proposal['payload']['proposed_target_quantities'].items() if q}|{'A','D','E'})
    files={'calendar.json':canonical(dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=sessions)),
           'ledger-identity.json':ledger_identity_source,
           'identity-evidence.json':canonical(dict(scope='explicit synthetic identity review',securities=needed))}
    identities={sid:dict(security_id=sid,ticker=sid,issuer_id='issuer-'+sid,exchange='NMS',currency='USD',
        identity_reviewed=True,source_hashes={'identity-evidence.json':digest(files['identity-evidence.json'])}) for sid in needed}
    files['identities.json']=canonical(dict(schema='SAVED_FRONTIER_REVIEWED_IDENTITIES_V1',securities=identities))
    histories={}; raw_by_security={}; unit_reviews={}
    prices={'A':[100,70,71],'B':[100,101,102],'D':[50,50,50],'E':[20,20,20]}
    for sid in needed:
        raw_path='raw/'+sid+'.json'; unit_path='units/'+sid+'.json'
        raw_by_security[sid]=raw_path; unit_reviews[sid]=unit_path
        files[raw_path]=canonical(dict(chart=dict(error=None,result=[dict(
            meta=dict(symbol=sid,currency='USD',exchangeName='NMS',instrumentType='EQUITY'),
            timestamp=[int(datetime.fromisoformat(row['open']).timestamp()) for row in sessions[:3]],events={},
            indicators=dict(quote=[dict(close=prices[sid])],adjclose=[dict(adjclose=prices[sid])]))])))
        files[unit_path]=canonical(dict(schema='SAVED_FRONTIER_CONSTANT_UNIT_REVIEW_V1',security_id=sid,ticker=sid,
            target_id=target['target_id'],proposal_id=proposal['proposal_id'],raw_sha256=digest(files[raw_path]),
            identity_sha256=digest(files['identities.json']),currency='USD',basis_id='unit-'+sid,
            price_basis='UNADJUSTED_USD',unresolved_units=[],pending_rights=[],corporate_actions=[],
            covered_from=sessions[0]['open'],covered_through=sessions[2]['close'],reviewed_at=reviewed))
        histories[sid]=dict(source_reference='sha256:'+digest(files[raw_path]),
            units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',unit_asof=days[2],currency='USD',
                       basis_id='unit-'+sid,review_reference=unit_path),
            closes=[dict(date=row['date'],close=str(price),completed_at=row['close'])
                    for row,price in zip(sessions[:3],prices[sid])])
    inputs=dict(base_target=dict(origin_reference=proposal['proposal_id'],monthly_decision_date=days[0],
        quantities={sid:proposal['payload']['proposed_target_quantities'].get(sid,0) for sid in needed},
        price_units={sid:'unit-'+sid for sid in needed}),signal_date=days[2],observed_at=reviewed,
        session_dates=days[:3],session_close_times=dict(review_reference='calendar.json',
            closes={row['date']:row['close'] for row in sessions[:3]}),histories=histories)
    files['normalized.json']=canonical(inputs)
    review=dict(schema='SAVED_FRONTIER_DAILY_REVIEW_V1',target_id=target['target_id'],proposal_id=proposal['proposal_id'],
        account_id=state['account_id'],account_revision=state['revision'],risk_state_sha256=digest(canonical(risk_state)),
        normalization_reviewed=True,unresolved_units=[],pending_rights=[],review_scope='FULL_WINDOW_CONSTANT_UNITS_NO_ACTIONS',
        source_received_at=received,reviewed_at=reviewed,monthly_decision_date=days[0],
        documents=dict(calendar='calendar.json',identities='identities.json',normalized_inputs='normalized.json',
                       raw_by_security=raw_by_security,unit_reviews=unit_reviews),
        source_sha256={name:digest(raw) for name,raw in files.items()})
    review_bytes=canonical(review)
    return dict(root=root,accounts=accounts,state=state,target=target,proposal=proposal,source_files=source_files,
        research_root=research_root,risk_path=risk_path,risk_state=risk_state,review_bytes=review_bytes,
        trusted_review_sha256=digest(review_bytes),files=files,now=current,created_at=created)


def arguments(case):
    return dict(research_root=case['research_root'],target_id=case['target']['target_id'],state=case['state'],
        risk_state=case['risk_state'],review_bytes=case['review_bytes'],trusted_review_sha256=case['trusted_review_sha256'],
        files=case['files'],now=case['now'],enabled=True)


class SavedFrontierDailyEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder=TemporaryDirectory(prefix='frontier-evidence-test-',dir=Path(__file__).resolve().parents[1]/'tmp')
        self.case=joint_fixture(self.folder.name)
    def tearDown(self):self.folder.cleanup()

    def test_joint_full_domain_raw_verified_without_mutating_original_or_databases(self):
        c=self.case; before=(c['accounts'].path.read_bytes(),c['risk_path'].read_bytes(),deepcopy(c['target']))
        result=verify_saved_frontier_daily_evidence(**arguments(c))
        self.assertEqual(result['status'],'SAVED_FRONTIER_DAILY_EVIDENCE_READY')
        self.assertEqual(result['required_security_ids'],['A','B','D','E'])
        self.assertEqual(c['target']['payload']['target_quantities'],{'A':199})
        self.assertEqual(result['proposed_target_quantities'],{'A':99,'B':99})
        self.assertIn('A',c['risk_state']['exited'])
        self.assertEqual((c['accounts'].path.read_bytes(),c['risk_path'].read_bytes(),c['target']),before)

    def test_raw_change_even_with_new_review_hash_cannot_disagree_with_normalized_values(self):
        c=self.case; values=arguments(c); files=deepcopy(c['files'])
        raw=json.loads(files['raw/B.json']);raw['chart']['result'][0]['indicators']['quote'][0]['close'][1]=105
        raw['chart']['result'][0]['indicators']['adjclose'][0]['adjclose'][1]=105
        files['raw/B.json']=canonical(raw)
        unit=json.loads(files['units/B.json']);unit['raw_sha256']=digest(files['raw/B.json']);files['units/B.json']=canonical(unit)
        inputs=json.loads(files['normalized.json']);inputs['histories']['B']['source_reference']='sha256:'+digest(files['raw/B.json'])
        files['normalized.json']=canonical(inputs)
        review=json.loads(c['review_bytes']);review['source_sha256']={n:digest(r) for n,r in files.items()}
        values.update(files=files,review_bytes=canonical(review),trusted_review_sha256=digest(canonical(review)))
        with self.assertRaisesRegex(ValueError,'FRONTIER_RAW_NORMALIZED_MISMATCH'):
            verify_saved_frontier_daily_evidence(**values)

    def test_missing_each_required_security_and_source_tampering_rejected(self):
        c=self.case
        for sid in ['A','B','D','E']:
            values=arguments(c);values['files']=dict(c['files']);values['files'].pop('raw/'+sid+'.json')
            with self.subTest(sid=sid),self.assertRaises(ValueError):verify_saved_frontier_daily_evidence(**values)
        values=arguments(c);values['files']=dict(c['files']);values['files']['calendar.json']+=b' '
        with self.assertRaisesRegex(ValueError,'FRONTIER_SOURCE_HASH'):verify_saved_frontier_daily_evidence(**values)

    def test_wrong_proposal_risk_snapshot_unit_and_future_session_rejected(self):
        c=self.case
        for key,value in [('proposal_id','f'*64),('risk_state_sha256','f'*64),('monthly_decision_date','2026-10-21')]:
            review=json.loads(c['review_bytes']);review[key]=value;raw=canonical(review)
            values=arguments(c);values.update(review_bytes=raw,trusted_review_sha256=digest(raw))
            with self.subTest(key=key),self.assertRaises(ValueError):verify_saved_frontier_daily_evidence(**values)
        values=arguments(c);values['now']='2026-10-24T14:00:00+00:00'
        with self.assertRaises(ValueError):verify_saved_frontier_daily_evidence(**values)

    def test_default_disabled_never_reads_archive_or_sources(self):
        values=arguments(self.case);values.pop('enabled')
        values.update(research_root='does-not-exist',files=None,review_bytes=None)
        with patch('data.saved_frontier_daily_evidence.read_saved_frontier_policy',side_effect=AssertionError('IO')):
            self.assertEqual(verify_saved_frontier_daily_evidence(**values)['status'],'SAVED_FRONTIER_DAILY_DISABLED')

    def test_resigned_actions_units_identity_and_short_window_cannot_bypass_review(self):
        c=self.case
        def checked(files):
            review=json.loads(c['review_bytes']);review['source_sha256']={name:digest(raw) for name,raw in files.items()}
            values=arguments(c);values.update(files=files,review_bytes=canonical(review),
                                             trusted_review_sha256=digest(canonical(review)))
            return verify_saved_frontier_daily_evidence(**values)
        for mode in ['action','symbol','unit-change','short-window','ledger-source']:
            files=dict(c['files'])
            if mode in ['action','symbol']:
                raw=json.loads(files['raw/B.json'])
                series=raw['chart']['result'][0]
                if mode=='action':series['events']={'splits':{'1':{'numerator':2,'denominator':1}}}
                else:series['meta']['symbol']='WRONG'
                files['raw/B.json']=canonical(raw)
                unit=json.loads(files['units/B.json']);unit['raw_sha256']=digest(files['raw/B.json'])
                files['units/B.json']=canonical(unit)
                inputs=json.loads(files['normalized.json']);inputs['histories']['B']['source_reference']='sha256:'+unit['raw_sha256']
                files['normalized.json']=canonical(inputs)
            elif mode=='unit-change':
                unit=json.loads(files['units/A.json']);unit['basis_id']='different-unit';files['units/A.json']=canonical(unit)
                inputs=json.loads(files['normalized.json']);inputs['base_target']['price_units']['A']='different-unit'
                inputs['histories']['A']['units']['basis_id']='different-unit';files['normalized.json']=canonical(inputs)
            elif mode=='short-window':
                unit=json.loads(files['units/B.json']);unit['covered_from']='2026-10-21T13:30:00+00:00'
                files['units/B.json']=canonical(unit)
            else:files['ledger-identity.json']=b'{}'
            with self.subTest(mode=mode),self.assertRaises(ValueError):checked(files)


if __name__=='__main__':unittest.main()
