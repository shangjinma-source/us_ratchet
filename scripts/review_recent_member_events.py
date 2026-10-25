"""Reproduce bounded 2021-2023 community/official event comparison; no admission."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tmp/free_history_sources_20261025_v1/nasdaq100_components_history.csv'
DESTINATION = ROOT / 'tmp/qqq_20201231_anchor_20261025/recent_member_event_review.json'
BASE = 'https://ir.nasdaq.com/news-releases/news-release-details/'
# Manually transcribed facts from primary notices, reviewed 2026-10-25.
# Dates are notice publication dates (US dateline), not first-ever disclosure claims.
EVIDENCE = [
 ('2021-07-21','2021-07-14','2021-07-21','HON','ALXN','https://www.globenewswire.com/news-release/2021/07/15/2263173/6948/en/Honeywell-International-Inc-to-Join-the-NASDAQ-100-Index-Beginning-July-21-2021.html'),
 ('2021-08-26','2021-08-23','2021-08-26','CRWD','MXIM','https://www.globenewswire.com/news-release/2021/08/24/2285158/0/en/CrowdStrike-Holdings-Inc-to-Join-the-NASDAQ-100-Index-Beginning-August-26-2021.html'),
 ('2021-12-20','2021-12-10','2021-12-20','ABNB DDOG FTNT LCID PANW ZS','CDW CERN CHKP TCOM FOX FOXA INCY','https://www.nasdaq.com/press-release/annual-changes-to-the-nasdaq-100-indexr-2021-12-10-0'),
 ('2022-01-24','2022-01-13','2022-01-24','ODFL','PTON',BASE+'old-dominion-freight-line-inc-join-nasdaq-100-index-beginning'),
 ('2022-02-02','2022-02-03','2022-02-02','CEG','',BASE+'constellation-energy-corp-joined-nasdaq-100-index-february-2'),
 ('2022-02-22','2022-02-10','2022-02-22','AZN','XLNX',BASE+'astrazeneca-plc-adr-join-nasdaq-100-index-beginning-february-22'),
 ('2022-06-09','2022-05-31','2022-06-09','META','FB','https://investor.atmeta.com/investor-news/press-release-details/2022/Meta-Platforms-Inc.-to-Change-Ticker-Symbol-to-META-on-June-9/default.aspx'),
 ('2022-11-21','2022-11-11','2022-11-21','ENPH','OKTA',BASE+'enphase-energy-inc-join-nasdaq-100-index-beginning-november-21'),
 ('2022-12-19','2022-12-09','2022-12-19','BKR CSGP FANG GFS RIVN WBD','BIDU DOCU MTCH NTES SPLK SWKS VRSN',BASE+'annual-changes-nasdaq-100-index-10'),
 ('2023-06-07','2023-05-30','2023-06-07','GEHC','FISV','https://ir.nasdaq.com/node/106206/pdf'),
 ('2023-06-20','2023-06-09','2023-06-20','ON','RIVN',BASE+'onsemi-join-nasdaq-100-index-beginning-june-20-2023'),
 ('2023-07-17','2023-07-12','2023-07-17','TTD','ATVI','https://ir.nasdaq.com/node/106501/pdf'),
 ('2023-12-14','2023-12-12','2023-12-18','TTWO','SGEN','https://ir.nasdaq.com/node/106911/pdf'),
 ('2023-12-18','2023-12-08','2023-12-18','CCEP CDW DASH MDB ROP SPLK','ALGN EBAY ENPH JD LCID ZM','https://ir.nasdaq.com/node/106896/pdf'),
]


def build_review():
    snapshots = list(csv.DictReader(SOURCE.open(encoding='utf-8-sig')))
    previous = None
    changes = {}
    for row in snapshots:
        current = set(row['tickers'].split(','))
        if '2021-01-01' <= row['date'] <= '2023-12-31':
            if previous is None:
                raise ValueError('Missing preceding member snapshot')
            changes[row['date']] = (current - previous, previous - current)
        previous = current
    if set(changes) != {item[0] for item in EVIDENCE}:
        raise ValueError('Evidence dates do not cover actual community event queue')
    records = []
    for community_date, announced, effective, added, removed, url in EVIDENCE:
        actual_added, actual_removed = changes[community_date]
        official_added, official_removed = set(added.split()), set(removed.split())
        normalize = lambda values: {'TCOM' if ticker == 'CTRP' else ticker for ticker in values}
        record = dict(community_effective_date=community_date, notice_publication_date=announced,
                      official_effective_date=effective, effective_phase='BEFORE_OPEN',
                      community_added=sorted(actual_added), community_removed=sorted(actual_removed),
                      official_added=sorted(official_added), official_removed=sorted(official_removed),
                      source_url=url, source_kind='PRIMARY_NOTICE_WEB_REVIEW',
                      date_matches=community_date == effective,
                      literal_members_match=(actual_added == official_added and actual_removed == official_removed),
                      members_match_with_explicit_ctrp_alias=(normalize(actual_added) == official_added and normalize(actual_removed) == official_removed),
                      last_trading_date=None, tradability_verified=False, admitted_for_backtest=False)
        if community_date == '2022-02-02':
            record.update(effective_phase='UNSPECIFIED_IN_NOTICE', warning='Retrospective notice: not evidence of pre-effective knowledge; EXC spin-off, no removal.')
        if community_date == '2022-06-09':
            record.update(event_type='TICKER_RENAME_NOT_ISSUER_REPLACEMENT', warning='CUSIP unchanged; do not model as issuer replacement.')
        if community_date == '2023-12-14':
            record.update(last_trading_date='2023-12-13', tradability_verified=True,
                          tradability_source='https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2023-721',
                          warning='SGEN halted on merger date Dec14; suspension Dec15; membership replacement Dec18.')
        if not record['literal_members_match']:
            record['alias_evidence'] = 'https://www.sec.gov/Archives/edgar/data/1269238/000119312519274119/d814130dex991.htm'
        records.append(record)
    return dict(status='NOT_ADMITTED', scope=['2021-01-01','2023-12-31'],
                community_source=str(SOURCE.relative_to(ROOT)), community_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                records=records, limitations=['Only the community event queue was checked; absence of omitted events is not proven.',
                'Fund holdings anchor is not automatically an index constituent certification.',
                'Membership exits do not determine last trading dates; price identity/actions still separate.',
                'Web-reviewed factual transcription is not frozen raw HTTP HTML.'])


if __name__ == '__main__':
    result = build_review()
    DESTINATION.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'events':len(result['records']), 'date_mismatches':sum(not r['date_matches'] for r in result['records']), 'literal_member_mismatches':sum(not r['literal_members_match'] for r in result['records'])}))
