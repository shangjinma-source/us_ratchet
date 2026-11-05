"""Real monthly selection and archive followed by native daily raw/risk admission."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json,unittest
import test_split_monthly_factory_20261105 as fixture
from core.strategy_account_ledger import canonical
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.saved_frontier_policy_archive import archive_saved_frontier_policy,read_saved_frontier_policy
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView,SavedFrontierProposalStore
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from docs.candidates import split_native_month_daily_20261105 as native
ROOT=Path(__file__).resolve().parents[1]
def digest(raw):return sha256(raw).hexdigest()
class Tests(unittest.TestCase):
 def case(self,folder):
  monthly,store,proof=fixture.Tests().case(folder,True,'AS_TRADED');captured={}
  original=monthly.selection.provider
  provider=next(c.cell_contents for c in original.__closure__ if isinstance(c.cell_contents,fixture.factory.SplitProvider))
  timing=next(c.cell_contents for c in provider._assemble.__func__.__closure__ if isinstance(c.cell_contents,dict) and 'split-B' in c.cell_contents)
  def capture(state):
   value=original(state);captured.update(value['source_package']['files']);return value
  monthly.selection.provider=capture
  view=SavedFrontierMonthlyView(monthly=monthly,proposals=SavedFrontierProposalStore(Path(folder)/'proposals.sqlite3'),validate_sources=monthly.selection._pins)
  target=view.generate(event_id='native',reason='INITIAL',expected_revision=store.read()['revision'],previous_target_id=None)
  proposal=view.require_proposal(target_id=target['target_id'],expected_proposal_id=target['proposal_id'])
  target=monthly.current()
  for name in target['payload']['runtime_pins']:captured[name]=(monthly.selection.root/name).read_bytes()
  research=Path(folder)/'archive';research.mkdir()
  archive_saved_frontier_policy(research_root=research,target=target,proposal=proposal,source_files=captured,enabled=True)
  calendar=deepcopy(timing['split-B']['calendar'])
  for day in ['2026-11-02','2026-11-03']:
   calendar['sessions'].append(dict(date=day,open=day+'T13:30:00+00:00',close=day+'T20:00:00+00:00'))
  now='2026-11-03T15:00:00+00:00';received='2026-11-03T14:00:00+00:00';epoch='2026-10-30'
  sessions=calendar['sessions'];completed=sessions[:-1];window=[r for r in completed if r['date']>=epoch]
  binding=target['payload']['decision']['payload']['input_binding'];state=store.read()
  domain=sorted({'B'}|{s for s,q in proposal['payload']['proposed_target_quantities'].items() if q}|{s for s,q in state['shares'].items() if q})
  files={'calendar':canonical(calendar),'identity-source':b'controlled source identity'}
  for event in state['events']:
   for name in event['payload'].get('identity_evidence',{}).get('source_hashes',{}):files[name]=captured[name] if name in captured else (monthly.selection.root/name).read_bytes()
  identities={s:dict(security_id=s,ticker=binding['marks'][s]['ticker'],issuer_id=binding['search_arguments']['metadata'].get(s,{}).get('issuer_id','held-issuer'),currency='USD',exchange='NMS',identity_reviewed=True,source_hashes={'identity-source':digest(files['identity-source'])}) for s in domain}
  files['identities']=canonical(dict(schema='SAVED_FRONTIER_REVIEWED_IDENTITIES_V1',securities=identities))
  riskpath=research/'risk.sqlite3';risk=MonthlyPeakExitStore(riskpath)
  risk.advance(account_id=state['account_id'],expected_previous_session=None,observations=[dict(decision_date='2026-10-29',session_date='2026-10-29',closes={'B':'10'},unit_ids={'B':'new'},evidence_sha256='a'*64)],baseline_targets={'B':1},target_month='2026-10')
  review=dict(schema='SPLIT_NATIVE_MONTH_DAILY_REVIEW_V1',target_id=target['target_id'],proposal_id=proposal['proposal_id'],account_id=state['account_id'],account_revision=state['revision'],risk_state_sha256=digest(canonical(risk.read(state['account_id']))),normalization_reviewed=True,unresolved_units=[],pending_rights=[],review_scope='FULL_WINDOW_NATIVE_POST_SPLIT_UNITS',source_received_at=received,reviewed_at=received,monthly_decision_date=epoch,timing_bundles=timing)
  checked=native.verify_native_units(state=state,target=target,archived=read_saved_frontier_policy(research_root=research,target_id=target['target_id']),review=review,now=now)
  histories={};rawpaths={};units={};priceunits={}
  for sid in domain:
   unit='new' if sid=='B' else 'unit-'+sid;priceunits[sid]=unit;rawpath='raw-'+sid;unitpath='unit-'+sid;rawpaths[sid]=rawpath;units[sid]=unitpath
   price=binding['marks'][sid]['price'];prices=[float(price)]*len(window)
   files[rawpath]=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=identities[sid]['ticker'],currency='USD',exchangeName='NMS',instrumentType='EQUITY'),timestamp=[int(datetime.fromisoformat(r['open']).timestamp()) for r in window],events={},indicators=dict(quote=[dict(close=prices)],adjclose=[dict(adjclose=prices)]))])))
   nr=dict(security_id=sid,raw_sha256=digest(files[rawpath]),review_reference=unitpath,price_basis='AS_TRADED',basis_asof=received,captured_at=received,current_unit_id=unit,split_schedule=[],reviewed_dividends=[])
   files[unitpath]=canonical(dict(schema='SPLIT_NATIVE_MONTH_UNIT_REVIEW_V1',security_id=sid,ticker=identities[sid]['ticker'],target_id=target['target_id'],proposal_id=proposal['proposal_id'],raw_sha256=digest(files[rawpath]),identity_sha256=digest(files['identities']),currency='USD',basis_id=unit,price_basis=binding['current_price_basis'],unresolved_units=[],pending_rights=[],native_unit_proof_sha256=checked['proof_sha256'],corporate_actions=[],raw_normalization=nr,covered_from=window[0]['open'],covered_through=window[-1]['close'],reviewed_at=received))
   histories[sid]=dict(source_reference='sha256:'+digest(files[rawpath]),units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',unit_asof=window[-1]['date'],currency='USD',basis_id=unit,review_reference=unitpath),closes=[dict(date=r['date'],close=str(price),completed_at=r['close']) for r in window])
  inputs=dict(base_target=dict(origin_reference=proposal['proposal_id'],monthly_decision_date=epoch,quantities={s:proposal['payload']['proposed_target_quantities'].get(s,0) for s in domain},price_units=priceunits),signal_date=window[-1]['date'],observed_at=received,session_dates=[r['date'] for r in completed],session_close_times=dict(review_reference='calendar',closes={r['date']:r['close'] for r in completed}),histories=histories)
  files['normalized']=canonical(inputs);review.update(documents=dict(calendar='calendar',identities='identities',normalized_inputs='normalized',raw_by_security=rawpaths,unit_reviews=units),source_sha256={n:digest(r) for n,r in files.items()})
  args=dict(research_root=research,risk_path=riskpath,target_id=target['target_id'],state=state,review_bytes=canonical(review),trusted_review_sha256=digest(canonical(review)),files=files,now=now,enabled=True)
  return monthly,store,target,proposal,args
 def test_real_monthly_target_native_daily_risk(self):
  with TemporaryDirectory(dir=ROOT/'tmp') as folder:
   monthly,store,target,proposal,args=self.case(folder)
   previous=MonthlyPeakExitStore(args['risk_path']).read(store.read()['account_id'])
   oldprices=MonthlyPeakExitStore(args['risk_path']).recorded_prices(store.read()['account_id'],previous['decision_date'])
   result=native.project_native_month_daily(**args)
   self.assertEqual(result['status'],'DAILY_SIGNAL_READY')
   self.assertEqual(result['signal']['effective_target_quantities'],{s:proposal['payload']['proposed_target_quantities'].get(s,0) for s in json.loads(args['files']['normalized'])['base_target']['quantities']})
   self.assertEqual(store.read(),args['state']);self.assertEqual(monthly.current()['target_id'],target['target_id'])
   self.assertEqual(MonthlyPeakExitStore(args['risk_path']).recorded_prices(store.read()['account_id'],previous['decision_date']),oldprices)
   # Genuine cash append after immutable target generation; source review rebinds current state.
   store.append(dict(event_id='cash-after-native',kind='CASH_CONFIRM',amount='90',cash_basis='TOTAL_UNINVESTED'),expected_revision=store.read()['revision'])
   args['state']=store.read();review=json.loads(args['review_bytes'])
   review['account_revision']=args['state']['revision'];review['risk_state_sha256']=digest(canonical(MonthlyPeakExitStore(args['risk_path']).read(args['state']['account_id'])))
   checked=native.verify_native_units(state=args['state'],target=target,archived=read_saved_frontier_policy(research_root=args['research_root'],target_id=target['target_id']),review=review,now=args['now'])
   for name in review['documents']['unit_reviews'].values():
    unit=json.loads(args['files'][name]);unit['native_unit_proof_sha256']=checked['proof_sha256'];args['files'][name]=canonical(unit)
   review['source_sha256']={n:digest(r) for n,r in args['files'].items()};args.update(review_bytes=canonical(review),trusted_review_sha256=digest(canonical(review)))
   repeated=native.project_native_month_daily(**args)
   self.assertEqual(repeated['signal']['effective_target_quantities'],result['signal']['effective_target_quantities'])
   self.assertEqual(repeated['signal']['account_revision'],store.read()['revision'])
   # An independently rehashed unknown basis remains invalid; prior risk unchanged.
   before=MonthlyPeakExitStore(args['risk_path']).read(store.read()['account_id'])
   name=review['documents']['unit_reviews']['B'];unit=json.loads(args['files'][name]);unit['raw_normalization']['price_basis']='UNKNOWN';args['files'][name]=canonical(unit)
   review['source_sha256']={n:digest(r) for n,r in args['files'].items()};args.update(review_bytes=canonical(review),trusted_review_sha256=digest(canonical(review)))
   with self.assertRaisesRegex(ValueError,'EXPLICIT_RAW_PRICE_BASIS_REQUIRED'):native.project_native_month_daily(**args)
   self.assertEqual(MonthlyPeakExitStore(args['risk_path']).read(store.read()['account_id']),before)
if __name__=='__main__':unittest.main()
