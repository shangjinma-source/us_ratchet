"""Pair only the 18 frozen early momentum dividend gaps with issuer evidence."""
import json
from pathlib import Path
from fractions import Fraction as F
from hashlib import sha256

ROOT=Path(__file__).resolve().parents[2]
OUTPUT='tmp/momentum_early_dividends_20261105'
INVENTORY='tmp/momentum_action_inventory_20261105/inventory.json'
SOURCES={
 'AMAT':'https://ir.appliedmaterials.com/stock-information/dividend-history/',
 'LRCX':'https://investor.lamresearch.com/dividend-history',
 'NXPI':'https://media.nxp.com/news-releases/news-release-details/nxp-semiconductors-announces-quarterly-dividend-6/',
 'NVDA':'https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-second-quarter-fiscal-2022',
 'MU':'https://investors.micron.com/news/press-release/2021/Micron-Initiates-a-Quarterly-Cash-Dividend-08-02-2021/default.aspx',
 'INTU2021':'https://www.sec.gov/Archives/edgar/data/896878/000089687821000233/intu-20210731.htm',
 'INTU2022':'https://www.sec.gov/Archives/edgar/data/896878/000119312521342279/d241331d424b7.htm',
 'KLAC':'https://ir.kla.com/sec-filings/all-sec-filings/content/0000319201-22-000006/klac-20211231.htm',
 'GILD':'https://www.gilead.com/news/news-details/2023/gilead-sciences-announces-27-percent-increase-in-first-quarter-2023-dividend',
 'ROST':'https://www.sec.gov/Archives/edgar/data/745732/000074573223000004/q4fy22exhibit991.htm',
 'SBUX':'https://investor.starbucks.com/news/financial-releases/news-details/2023/Starbucks-Declares-Quarterly-Cash-Dividend-040323/default.aspx',
 'AVGO':'https://www.sec.gov/Archives/edgar/data/1730168/000173016823000093/avgo-10292023x8kxex99.htm',
 'ASML':'https://adr.api.wsod.com/jpmadr-public/v1/dr/dividends/N07059210?limit=25&offset=0&announcementFilter=final',
}
# issuer nominal USD amounts, not provider split-adjusted amounts
TABLE=[
 ('AMAT','2021-05-26','2021-06-17','.24','AMAT','2021-05-27'),
 ('AMAT','2021-08-25','2021-09-16','.24','AMAT','2021-08-26'),
 ('AMAT','2021-11-24','2021-12-16','.24','AMAT','2021-11-26'),
 ('LRCX','2021-06-15','2021-07-07','1.30','LRCX','2021-06-16'),
 ('LRCX','2021-09-27','2021-10-13','1.50','LRCX','2021-09-28'),
 ('LRCX','2023-09-12','2023-10-04','2.00','LRCX','2023-09-13'),
 ('NXPI','2021-06-14','2021-07-06','.5625','NXPI','2021-06-15'),
 ('NVDA','2021-08-31','2021-09-23','.04','NVDA','2021-09-01'),
 ('MU','2021-09-30','2021-10-18','.10','MU','2021-10-01'),
 ('INTU','2021-10-07','2021-10-18','.68','INTU2021','2021-10-11'),
 ('INTU','2022-01-07','2022-01-18','.68','INTU2022','2022-01-10'),
 ('KLAC','2021-11-12','2021-12-01','1.05','KLAC','2021-11-15'),
 ('GILD','2023-03-14','2023-03-30','.75','GILD','2023-03-15'),
 ('ROST','2023-03-13','2023-03-31','.335','ROST','2023-03-14'),
 ('SBUX','2023-05-11','2023-05-26','.53','SBUX','2023-05-12'),
 ('AVGO','2023-09-20','2023-09-29','4.60','AVGO','2023-09-21'),
 ('AVGO','2023-12-19','2023-12-29','5.25','AVGO','2023-12-20'),
 ('ASML','2021-11-02','2021-11-12','2.08431','ASML','2021-11-03'),
]

def digest(path):return sha256((ROOT/path).read_bytes()).hexdigest()

def main():
    output=ROOT/OUTPUT;output.mkdir(exist_ok=True)
    inventory=json.loads((ROOT/INVENTORY).read_bytes())
    needed={}
    for item in inventory['unique_remaining']:
        event=item['event']
        if item['window']=='2021_2023' and isinstance(event,dict) and event.get('kind')=='dividends':
            needed.setdefault((event['security_id'],event['date']),[]).append(event)
    assert len(needed)==len(TABLE)==18
    pins={INVENTORY:digest(INVENTORY),Path(__file__).relative_to(ROOT).as_posix():sha256(Path(__file__).read_bytes()).hexdigest()}
    api_path='tmp/asml_remaining_dividend_review_20261105/jpm_final_dividends.json'
    pins[api_path]=digest(api_path)
    notice=next(x for x in json.loads((ROOT/api_path).read_bytes())['data']['items'] if x.get('recordDate','').startswith('2021-11-03'))
    assert notice['status']=='Final' and notice['ratio']=='1:1' and notice['announcementDate'].startswith('2021-11-03') and notice['paymentDate'].startswith('2021-11-12')
    assert F(str(notice['ratePerDr']))==F('2.08431')==F(str(notice['underlying']['currencyPerDr']))*F(str(notice['underlying']['finalExchangeRate']))
    observations=[];reviews=[];events=[];gaps=[]
    for ticker,ex,pay,amount,key,record in sorted(TABLE,key=lambda x:(x[1],x[0])):
        sid='research:security:'+ticker.lower();observed=needed.pop((sid,ex));refs=[]
        for event in observed:
            assert event['ticker']==ticker and digest(event['source'])==event['source_sha256']
            pins[event['source']]=event['source_sha256'];refs.append(event['source'])
        ratio=F(amount)/F(str(observed[0]['provider_event']['amount']))
        unit=('NOMINAL_COMMON_PRE_FUTURE_10_FOR_1_SPLIT' if ticker in ('LRCX','KLAC','AVGO') else
              'NOMINAL_COMMON_AFTER_2021_FOUR_FOR_ONE_BEFORE_2024_TEN_FOR_ONE' if ticker=='NVDA' else
              'NY_REGISTERED_SHARE_ONE_TO_ONE_FINAL_GROSS_USD' if ticker=='ASML' else 'NOMINAL_ORDINARY_COMMON_SHARE')
        observation=dict(ticker=ticker,security_id=sid,ex_date=ex,ex_date_basis='FROZEN_PROVIDER_EVENT; issuer history also supplies exdate for AMAT/LRCX',record_date=record,payment_date=pay,amount_per_share=str(F(amount)),currency='USD',url=SOURCES[key],nominal_unit=unit)
        if ticker=='AVGO' and ex=='2023-09-20':
            observation['record_date_basis']='Provider exdate only; cited Q4 issuer release confirms actual September29 payment and $4.60, not recorddate.'
            observation['record_date']=None
        if ticker=='ASML':observation['final_notice']=notice;refs.append(api_path)
        observations.append(observation)
        row=dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=str(F(amount)),currency='USD',source_references=[OUTPUT+'/official_observations.json',*refs],observed_provider_events=observed,official_url=SOURCES[key],nominal_unit=unit,nominal_to_provider_amount_ratio=str(ratio))
        if ticker=='NXPI':row['amount_resolution']='ISSUER_EXACT_0.5625_OVERRIDES_PROVIDER_ROUNDED_0.563'
        if ticker=='ASML':row.update(amount_resolution='JPM_FINAL_GROSS_2.08431_OVERRIDES_ROUNDED_2.084',final_announcement_date='2021-11-03',posthoc_equity=True)
        reviews.append(row)
        events.append(dict(event_id='momentum-early-gross:'+sid+':'+ex,security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=str(F(amount)),withholding_rate='0',currency='USD',assumption='GROSS_RESEARCH; ISSUER_PAYMENT_SESSION_CLOSE_NOT_BROKER_CREDIT; NO_UNIT_OR_SPLIT_ADMISSION'))
        gaps.append(dict(security_id=sid,ex_date=ex,status='PAIRED_EVIDENCE',nominal_amount=str(F(amount)),provider_amount=str(observed[0]['provider_event']['amount']),payment_date=pay))
    assert not needed
    observation_path=OUTPUT+'/official_observations.json'
    (ROOT/observation_path).write_text(json.dumps(dict(retrieval='2026-11-05 web parsed issuer/SEC primary observations; paraphrased fields, not saved raw HTTP except existing JPM API',rows=observations),indent=2),encoding='utf8')
    pins[observation_path]=digest(observation_path)
    report=dict(status='REVIEWED_18_EARLY_DIVIDEND_PAIRS_NOT_FULL_ECONOMIC_ADMISSION',source_hashes=pins,review_rows=reviews,dividend_events=events,gaps=gaps,unresolved_dividends=[],scope='Only exact frozen early SID/exdate gaps. No split, merger, spin-off, source-coordinate or identity admission.',limitations=['Conditional research SID and execution nominal price coordinates remain original assumptions; corporate-action gate still required.','ASML final known Nov3 after Nov2 exdate: exdate exact receivable is retrospective accounting, not PIT signal. Must separately show no decision uses that one-day receivable; not proved by this evidence supplement.','Gross no-withholding matches research; NXPI/ASML actual withholding and HSBC credit are not modeled.','Provider exdate retained, never replaced by issuer recorddate.'])
    path=output/'supplement.json';path.write_text(json.dumps(report,indent=2),encoding='utf8')
    (output/'gap_table.json').write_text(json.dumps(gaps,indent=2),encoding='utf8')
    print(json.dumps(dict(path=path.relative_to(ROOT).as_posix(),sha256=sha256(path.read_bytes()).hexdigest(),pairs=len(events))))

if __name__=='__main__':main()
