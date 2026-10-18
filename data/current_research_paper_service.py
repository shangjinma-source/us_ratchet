"""Saved-price paper interface. No search, broker IO, or production account access."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone, date
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from zoneinfo import ZoneInfo

from data.current_portfolio_preview import ROOT
from data.current_research_snapshot_resolver import read_known_research_snapshot
from data.current_top1_portfolio_research import RESEARCH_VERSION as TOP1_RESEARCH_VERSION
from backtest.return_priority_monthly_top1_selector import VERSION as TOP1_METHOD
from data.current_research_limit_plan import build_current_research_limit_plan
from data.current_research_fill_ledger import review_paper_ledger
from data.current_research_paper_store import ResearchPaperStore
from data.current_research_plan_observation import review_plan_bound_observations
from data.current_research_observation_registry import review_registered_plan_observations

RAW_DIRECTORY = 'data/cache/research/current_raw_capture_20261014_v1'
INDEX_SHA = '6c4edd3fa4d6288e3bdebe8a042f7d96abf13cc1dc91e31d3a6c992e442cc767'
NY = ZoneInfo('America/New_York')


def require(ok, message):
    if not ok:
        raise ValueError(message)


class CurrentResearchPaperService:
    def __init__(self, *, snapshot=None, directory=None, clock=None, root=ROOT):
        self.root = Path(root)
        self.directory = Path(directory) if directory is not None else self.root / 'data/research_paper'
        self.snapshot = snapshot or read_known_research_snapshot
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self):
        now = self.clock()
        require(isinstance(now, datetime) and now.tzinfo is not None, '服务时钟必须包含时区')
        return now.astimezone(NY)

    def _read_pin(self, path, expected):
        raw = (self.root / path).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, '研究报价来源指纹不匹配')
        return raw

    def _quotes(self, snapshot):
        require(snapshot['as_of'] == '2026-10-13', '仅支持已保存的10月13日至14日交易日历')
        index_path = RAW_DIRECTORY + '/completion_index_104.json'
        index = json.loads(self._read_pin(index_path, INDEX_SHA))
        entries = {row['ticker']: row for row in index['entries']}
        pins = dict(snapshot['sources'])
        pins[index_path] = INDEX_SHA
        quotes, market = [], None
        # QQQ supplies the saved next-session times even for all-cash research.
        for stock in [dict(ticker='QQQ', security_id=None)] + snapshot['stocks']:
            ticker, sid = stock['ticker'], stock['security_id']
            require(ticker in entries, '研究股票没有已冻结报价来源')
            entry = entries[ticker]
            path = RAW_DIRECTORY + '/' + ticker + '.response.bin'
            receipt_path = RAW_DIRECTORY + '/' + ticker + '.receipt.json'
            raw = self._read_pin(path, entry['raw_sha256'])
            receipt = json.loads(self._read_pin(receipt_path, entry['receipt_sha256']))
            require(receipt['http_status'] == 200 and receipt['raw_sha256'] == entry['raw_sha256'], '报价回执不匹配')
            decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
            observation_path = RAW_DIRECTORY + '/' + ticker + '.decoded.json'
            observation = json.loads(self._read_pin(observation_path, entry['decoded_sha256']))
            require(observation['ticker'] == ticker and observation['receipt_sha256'] == entry['receipt_sha256'], '报价观测与回执不匹配')
            require(hashlib.sha256(decoded).hexdigest() == observation['decoded_sha256'], '解压报价指纹不匹配')
            pins[observation_path] = entry['decoded_sha256']
            result = json.loads(decoded, parse_float=Decimal)['chart']['result'][0]
            meta = result['meta']
            require(meta['symbol'] == ticker and meta['currency'] == 'USD' and meta['instrumentType'] == ('ETF' if sid is None else 'EQUITY'), '报价证券代码、币种或类别不匹配')
            require(meta['exchangeTimezoneName'] == 'America/New_York', '报价交易所时区不支持')
            regular = meta['currentTradingPeriod']['regular']
            opening = datetime.fromtimestamp(regular['start'], NY)
            closing = datetime.fromtimestamp(regular['end'], NY)
            require(opening.isoformat() == '2026-10-14T09:30:00-04:00' and closing.isoformat() == '2026-10-14T16:00:00-04:00', '保存的交易时段不符合已证日历')
            market = dict(date='2026-10-14', timezone='America/New_York', open_at=opening.isoformat(), close_at=closing.isoformat(), source=index_path)
            terminal_date = datetime.fromtimestamp(result['timestamp'][-1], NY).date().isoformat()
            price_date = datetime.fromtimestamp(meta['regularMarketTime'], NY).date().isoformat()
            price = Decimal(str(meta['regularMarketPrice']))
            close = Decimal(str(result['indicators']['quote'][0]['close'][-1]))
            require(terminal_date == price_date == snapshot['as_of'], '报价日期与冻结研究日期不一致')
            require(price.is_finite() and price > 0 and close.is_finite() and close.quantize(Decimal('.01')) == price.quantize(Decimal('.01')), '原始收盘与市场报价不一致')
            pins[path], pins[receipt_path] = entry['raw_sha256'], entry['receipt_sha256']
            if sid is not None:
                require(Decimal(str(stock['close'])).quantize(Decimal('.01')) == price.quantize(Decimal('.01')), '研究价格与保存报价不一致')
                quotes.append(dict(security_id=sid, price=format(price, 'f'), as_of=price_date,
                    price_kind='PROVIDER_REGULAR_MARKET_PRICE_DECIMAL', price_basis='CURRENT_SHARE_USD_REFERENCE_CONDITIONAL_NOT_LIVE', source_references=[path, receipt_path]))
        return quotes, pins, market

    def _read_account(self, account_id):
        require(isinstance(account_id, str) and re.fullmatch(r'paper-[0-9a-f]{24}', account_id), '纸面账户编号格式无效')
        path = self.directory / 'research_paper.sqlite3'
        require(path.is_file(), '纸面账户尚未开始')
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
            row = connection.execute('SELECT state_json FROM research_paper_accounts WHERE account_id=?', (account_id,)).fetchone()
        require(row is not None, '未找到纸面账户')
        state = json.loads(row[0])
        review_paper_ledger(state)
        require(state['account_id'] == account_id and account_id == 'paper-' + state['plans'][0]['plan_id'][:24], '纸面账户与冻结计划不匹配')
        return state

    def _response(self, state):
        review = review_paper_ledger(state)
        market = state['plan']['causal_inputs']['research_snapshot'].get('market_session')
        require(isinstance(market, dict), '纸面计划缺少已验证交易时段')
        active = state['plan']['active_date']
        require(market.get('date') == active and market.get('timezone') == 'America/New_York', '交易时段日期或时区与计划不符')
        try:
            opening = datetime.fromisoformat(market.get('open_at', ''))
            closing = datetime.fromisoformat(market.get('close_at', ''))
        except (TypeError, ValueError) as error:
            raise ValueError('交易时段开闭市时间格式无效') from error
        require(all(value.tzinfo is not None and value.date().isoformat() == active
                    and value.astimezone(NY).date().isoformat() == active
                    and value.utcoffset() == value.astimezone(NY).utcoffset()
                    for value in (opening, closing)) and opening < closing,
                '交易时段须为计划当日纽约时间且开盘早于收盘')
        review['expiry_authority'] = 'SERVER_CHECKED_SAVED_MARKET_CLOSE_FOR_API_EXPIRE'
        return dict(plan=deepcopy(state['plan']), account_id=state['account_id'],
                    genesis_plan_id=state['plans'][0]['plan_id'],
                    genesis_research_id=state['plans'][0]['research_id'],
                    market_session=deepcopy(market),
                    review=review, research_only=True, execution_blocked=True)

    def preview(self, research_id):
        snapshot = deepcopy(self.snapshot(research_id))
        require(snapshot['research_id'] == research_id and snapshot['status'] in ('AVAILABLE', 'ALL_CASH'), '研究结果不可用于纸面计划')
        quotes, pins, market = self._quotes(snapshot)
        frozen = dict(research_id=research_id, as_of=snapshot['as_of'], stocks=deepcopy(snapshot['stocks']), source_hashes=pins, market_session=market)
        is_top1 = snapshot.get('research_version') == TOP1_RESEARCH_VERSION
        if is_top1:
            require(snapshot.get('method') == TOP1_METHOD, '单股研究方法标识不匹配')
            frozen.update(selection_method=TOP1_METHOD, target_month='2026-10')
        plan = build_current_research_limit_plan(research_snapshot=frozen, quotes=quotes,
            available_cash=snapshot['budget_identity_exact']['entered_cash'], shares={},
            account_revision='PAPER_INITIAL_V1', decision_date='2026-10-13', active_date='2026-10-14',
            calendar=['2026-10-13', '2026-10-14'], strategy_version='PAPER_FROZEN_TOP1_V1' if is_top1 else 'PAPER_FROZEN_QUANTITY_V1',
            target_quantities={s['security_id']: s['units'] for s in snapshot['stocks']})
        require(plan['status'] == 'READY', '纸面计划不可用：' + str(plan.get('reason', '')))
        account_id = 'paper-' + plan['plan_id'][:24]
        review = None
        if (self.directory / 'research_paper.sqlite3').is_file():
            with closing(sqlite3.connect((self.directory / 'research_paper.sqlite3').resolve().as_uri() + '?mode=ro', uri=True)) as connection:
                exists = connection.execute('SELECT 1 FROM research_paper_accounts WHERE account_id=?', (account_id,)).fetchone()
            if exists:
                state = self._read_account(account_id)
                require(state['plans'][0] == plan, '已存纸面初始计划内容不匹配')
                return self._response(state)
        return dict(plan=plan, account_id=account_id, genesis_plan_id=plan['plan_id'], genesis_research_id=plan['research_id'],
                    market_session=market, review=review, research_only=True, execution_blocked=True)

    def start(self, research_id, expected_plan_id):
        response = self.preview(research_id)
        require(response['plan']['plan_id'] == expected_plan_id, '预览计划已变化，请重新预览后开始')
        state = ResearchPaperStore(self.directory).create(response['account_id'], response['plan'])
        return self._response(state)

    def account(self, account_id):
        return self._response(self._read_account(account_id))

    def review(self, account_id):
        """Read evidence bound to the current plan without refreshing market data."""
        state = self._read_account(account_id)
        response = self._response(state)
        now = self._now()
        observed = review_registered_plan_observations(state, root=self.root, now=now)
        response['market_review'] = observed if observed is not None else review_plan_bound_observations(
            state, root=self.root, now=now)
        return response

    def fill(self, account_id, event):
        response = self.account(account_id)
        require(isinstance(event, dict), '成交事件必须是对象')
        now = self._now()
        require(date.fromisoformat(event['session']) <= now.date(), '不能录入未来交易日的成交')
        require(now >= datetime.fromisoformat(response['market_session']['open_at']), '保存的交易时段尚未开盘，不能录入成交')
        return self._response(ResearchPaperStore(self.directory).record_fill(account_id, event))

    def order(self, account_id, event):
        response = self.account(account_id)
        require(isinstance(event, dict) and event.get('event_type') in ('CANCEL', 'EXPIRE'), '仅支持纸面撤销或到期事件')
        if event['event_type'] == 'EXPIRE':
            now = self._now()
            require(date.fromisoformat(event['completed_session']) <= now.date(), '不能声明未来交易日已完成')
            require(now >= datetime.fromisoformat(response['market_session']['close_at']), '保存的交易时段尚未收盘，不能标记到期')
        return self._response(ResearchPaperStore(self.directory).record_order_event(account_id, event))


SERVICE = CurrentResearchPaperService()
