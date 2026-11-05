"""Real durable gzip transport -> two source generations -> existing split risk."""
from copy import deepcopy
from contextlib import closing
from datetime import datetime,timedelta
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import gzip,json,sqlite3,unittest
from core.strategy_account_ledger import canonical
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_monthly_supplement_gzip_v1 import capture_supplement
from data.official_rss_gzip_transport_v1 import GzipRssTransport,URL
from data.current_quantity_v2_paper_action_sources import daily_url
from docs.candidates import split_frontier_supplement_20261105 as module
import test_split_saved_frontier_daily_20261105 as fixture
ROOT=fixture.ROOT

def digest(raw):return sha256(raw).hexdigest()
def pair_hash(parent,current,action):
 descriptor={key:{k:v for k,v in gen.items() if k!='capture'}|dict(capture={k:v for k,v in gen['capture'].items() if k!='files'}) for key,gen in [('parent',parent),('current',current)]}
 descriptor['action']=action
 return digest(canonical(descriptor))

class Tests(unittest.TestCase):
 def case(self,folder,basis='AS_TRADED',mutation=None):
  c,accounts,args=fixture.Tests().case(folder,basis);files=args['files'];review=json.loads(args['review_bytes']);inputs=json.loads(files['normalized.json'])
  identities=json.loads(files['identities.json'])['securities'];action=next(r['payload'] for r in accounts.read()['events'] if r['payload']['kind']=='SPLIT_CONFIRMED')
  sessions=[];day=datetime.fromisoformat('2026-09-01T13:30:00+00:00')
  while day.date().isoformat()<='2026-10-23':
   if day.weekday()<5:sessions.append(dict(date=day.date().isoformat(),open=day.isoformat(),close=day.replace(hour=20,minute=0).isoformat()))
   day+=timedelta(days=1)
  calendar=dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=sessions)
  # Synthetic fixed calendar is intentionally longer than twenty sessions.
  # Each transport clock advances; per-SID receipts are deliberately unequal.
  generations=[]
  for label,start,state in [('parent','2026-10-21T14:00:00+00:00',c['state']),('current','2026-10-23T14:00:00+00:00',accounts.read())]:
   time=[datetime.fromisoformat(start)]
   def clock():time[0]+=timedelta(milliseconds=10);return time[0]
   risk=MonthlyPeakExitStore(args['risk_path']).read(accounts.read()['account_id'])
   prepared=module.prepare_request(state=state,target=c['target'],proposal=c['proposal'],risk_state=risk,calendar=calendar,identities=identities,now=clock())
   gen_inputs=deepcopy(inputs);cutoff='2026-10-20' if label=='parent' else '2026-10-22'
   gen_inputs['signal_date']=cutoff;gen_inputs['session_dates']=[r['date'] for r in sessions if r['date']<=cutoff]
   gen_inputs['session_close_times']['closes']={r['date']:r['close'] for r in sessions if r['date']<=cutoff}
   raws={};reviews={}
   for sid,path in review['documents']['raw_by_security'].items():
    gen_inputs['histories'][sid]['units']['unit_asof']=cutoff
    doc=json.loads(files[path]);series=doc['chart']['result'][0];daily={datetime.fromtimestamp(t,datetime.fromisoformat(start).tzinfo).date().isoformat():v for t,v in zip(series['timestamp'],series['indicators']['quote'][0]['close'])}
    if label=='parent':
     series['events']={}
     if sid=='A':daily={d:str(F(v)*(8 if basis=='SPLIT_ADJUSTED_TO_CURRENT_UNIT' else 1)) for d,v in daily.items()};gen_inputs['base_target']['price_units'][sid]='unit-A';gen_inputs['histories'][sid]['units']['basis_id']='unit-A';gen_inputs['base_target']['quantities'][sid]=99
    raw_dates=[r for r in sessions if r['date']<=cutoff and r['open']>=prepared['request']['window_start']]
    series['timestamp']=[int(datetime.fromisoformat(r['close']).timestamp()) for r in raw_dates]
    values=[daily.get(r['date'],daily['2026-10-20']) for r in raw_dates]
    series['indicators']['quote'][0]['close']=values;series['indicators']['adjclose'][0]['adjclose']=values
    raws[sid]=canonical(doc)
    nr=deepcopy(json.loads(files[review['documents']['unit_reviews'][sid]])['raw_normalization'])
    if label=='parent':nr.update(price_basis='AS_TRADED',split_schedule=[],current_unit_id='unit-'+sid)
    reviews[sid]=nr
   def daily_fetch(ticker,begin,end):
    if mutation=='account_mid' and label=='current':accounts.append(dict(event_id='midcash',kind='CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED'),expected_revision=accounts.read()['revision'])
    return dict(status=200,url=daily_url(ticker,begin,end),body=raws[ticker])
   def rss_fetch():
    return dict(status=200,url=URL,headers={'Content-Encoding':'gzip'},body=gzip.compress(b'<rss><channel><title>Nasdaq</title><pubDate>Tue, 20 Oct 2026 13:00:00 GMT</pubDate><item><title>Unrelated</title><pubDate>Tue, 20 Oct 2026 13:00:00 GMT</pubDate></item></channel></rss>'))
   binding=prepared['binding']
   def read_binding():
    return dict(binding,account_revision=accounts.read()['revision']) if label=='current' else deepcopy(binding)
   with patch('socket.socket.connect',side_effect=AssertionError('NETWORK_FORBIDDEN')),patch('data.strategy_monthly_supplement_gzip_v1.GzipRssTransport',side_effect=lambda **kw:GzipRssTransport(fetch=rss_fetch,**kw)):
    capture=capture_supplement(directory=Path(folder)/label,request=prepared['request'],binding=binding,read_binding=read_binding,execute=True,fetch_daily=daily_fetch,clock=clock)
   for sid,path in capture['documents']['action_receipts'].items():
    receipt=json.loads(capture['files'][path]);reviews[sid].update(raw_sha256=receipt['raw_sha256'],captured_at=receipt['received_at'],basis_asof=receipt['received_at'])
   gen_inputs['observed_at']=capture['finished_at']
   generation=dict(capture=capture,request=prepared['request'],binding=binding,inputs=gen_inputs,reviews=reviews)
   generations.append(generation)
  parent,current=generations
  checked=module.review_generation(**current,identities=identities,now=current['capture']['finished_at'])
  normalized=checked['inputs'];received_map={}
  for sid,path in current['capture']['documents']['action_receipts'].items():
   receipt=json.loads(current['capture']['files'][path]);files[review['documents']['raw_by_security'][sid]]=current['capture']['files'][receipt['raw_path']];received_map[sid]=receipt['received_at']
   up=review['documents']['unit_reviews'][sid];unit=json.loads(files[up]);unit.update(raw_sha256=receipt['raw_sha256'],raw_normalization=current['reviews'][sid],reviewed_at=current['capture']['finished_at']);files[up]=canonical(unit)
  files['calendar.json']=canonical(calendar);files['normalized.json']=canonical(normalized)
  review.update(source_received_by_security=received_map,source_received_at=max(received_map.values()),reviewed_at=current['capture']['finished_at'],source_sha256={k:digest(v) for k,v in files.items()})
  args.update(review_bytes=canonical(review),trusted_review_sha256=digest(canonical(review)),now=current['capture']['finished_at'])
  return parent,current,action,args,accounts
 def test_real_capture_pair_then_risk_both_bases(self):
  for basis in ['AS_TRADED','SPLIT_ADJUSTED_TO_CURRENT_UNIT']:
   with self.subTest(basis=basis),TemporaryDirectory(dir=ROOT/'tmp') as folder:
    parent,current,action,args,accounts=self.case(folder,basis)
    old=canonical(parent['capture']['source_hashes']);state=accounts.read()
    answer=module.apply_capture_pair(parent=parent,current=current,trusted_pair_sha256=pair_hash(parent,current,action),reader_arguments=args,read_binding=lambda:current['binding'],now=args['now'])
    self.assertEqual(answer['status'],'DAILY_SIGNAL_READY');self.assertEqual(answer['signal']['effective_target_quantities']['A'],0)
    self.assertEqual(canonical(parent['capture']['source_hashes']),old);self.assertEqual(accounts.read(),state)
    self.assertEqual(answer['supplement_pair']['overlap_dates'],['2026-10-20'])
    self.assertEqual(len(set(json.loads(current['capture']['files'][p])['received_at'] for p in current['capture']['documents']['action_receipts'].values())),4)
 def test_bad_overlap_coverage_clocks_basis_actions_refused(self):
  with TemporaryDirectory(dir=ROOT/'tmp') as folder:
   parent,current,action,args,accounts=self.case(folder)
   identities=json.loads(args['files']['identities.json'])['securities']
   for mode,reason in [('overlap','SPLIT_PAIR_PRICE_CONTINUITY'),('missing','RAW_COMPLETE_WINDOW_REQUIRED'),('basis','EXPLICIT_RAW_PRICE_BASIS_REQUIRED'),('action','RAW_SPLIT_SCHEDULE_MISMATCH'),('clock','SUPPLEMENT_DAILY_CAPTURE_CLOCK'),('floor','SUPPLEMENT_DAILY_CAPTURE_CLOCK')]:
    with self.subTest(mode=mode):
     bad=deepcopy(current);capture=bad['capture'];path=capture['documents']['action_receipts']['A'];receipt=json.loads(capture['files'][path]);rawpath=receipt['raw_path']
     if mode in {'overlap','missing','action'}:
      doc=json.loads(capture['files'][rawpath]);series=doc['chart']['result'][0]
      idx=next(i for i,t in enumerate(series['timestamp']) if datetime.fromtimestamp(t,datetime.fromisoformat(args['now']).tzinfo).date().isoformat()=='2026-10-20')
      if mode=='overlap':series['indicators']['quote'][0]['close'][idx]='101'
      elif mode=='missing':
       series['timestamp'].pop(idx);series['indicators']['quote'][0]['close'].pop(idx);series['indicators']['adjclose'][0]['adjclose'].pop(idx)
      else:series['events']['splits']['extra']=dict(date=series['timestamp'][0],numerator=2,denominator=1,splitRatio='2:1')
      capture['files'][rawpath]=canonical(doc);capture['source_hashes'][rawpath]=digest(canonical(doc));receipt['raw_sha256']=digest(canonical(doc));bad['reviews']['A']['raw_sha256']=receipt['raw_sha256']
     elif mode=='basis':bad['reviews']['A']['price_basis']='UNKNOWN'
     elif mode=='clock':receipt['received_at']='2026-10-23T13:00:00+00:00';bad['reviews']['A']['captured_at']=receipt['received_at'];bad['reviews']['A']['basis_asof']=receipt['received_at']
     elif mode=='floor':bad['request']['observed_floor']='2026-10-23T15:00:00+00:00';capture['capture_id']=digest(canonical(dict(binding=bad['binding'],request=bad['request'])))
     capture['files'][path]=canonical(receipt);capture['source_hashes'][path]=digest(canonical(receipt))
     with self.assertRaisesRegex(ValueError,reason+'|SUPPLEMENT_OBSERVED_FLOOR'):
      module.review_pair(parent=parent,current=bad,identities=identities,action=action,trusted_pair_sha256=pair_hash(parent,bad,action),now=args['now'])
 def test_mid_capture_account_change(self):
  with TemporaryDirectory(dir=ROOT/'tmp') as folder:
   with self.assertRaisesRegex(ValueError,'SUPPLEMENT_SNAPSHOT_CHANGED'):self.case(folder,mutation='account_mid')

if __name__=='__main__':unittest.main()
