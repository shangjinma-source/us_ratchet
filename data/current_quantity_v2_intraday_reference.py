"""DI-only V2 multi-security reference; no HTTP, orders, accounts or default service.

Resolvers are server-owned. Hashes bind supplied bytes, not external authenticity.
Identity resolver supplies the existing reviewed manifest and pinned evidence;
this component does not certify historical target units or corporate-action completeness.
Each call recomputes a conservative reference, not an automatic order repricing rule.
"""
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from data.current_research_intraday_execution import decode_intraday_reference

VERSION = 'CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH'
METHOD = 'EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def exact(value):
    require(type(value) in (str, int), 'EXACT_NUMBER_REQUIRED')
    return Fraction(value)


class CurrentQuantityV2IntradayReference:
    """snapshot_reader(rid), input_reader(snapshot)->bytes,
    quote_reader(stock)->{raw:bytes,captured_at:aware datetime},
    identity_reader(snapshot,stock,session)->{manifest_path,source_hashes,files}.

    Manifest bytes must match snapshot sources and contain the selected reviewed
    SID/ticker/issuer. Its identity references must be supplied as pinned bytes.
    Current prices are conditional provider quotes, not certified exchange prices.
    """
    def __init__(self, *, snapshot_reader, input_reader, quote_reader, identity_reader, clock):
        self.snapshot_reader = snapshot_reader
        self.input_reader = input_reader
        self.quote_reader = quote_reader
        self.identity_reader = identity_reader
        self.clock = clock

    def preview(self, research_id):
        snapshot = deepcopy(self.snapshot_reader(research_id))
        require(snapshot.get('research_id') == research_id and snapshot.get('research_version') == VERSION
                and snapshot.get('method_version') == METHOD and snapshot.get('research_only') is True
                and snapshot.get('execution_blocked') is True and snapshot.get('orders_created') is False
                and snapshot.get('executable_buy_quantities') is None, 'V2_SNAPSHOT_REQUIRED')
        require(snapshot.get('status') in ('AVAILABLE', 'ALL_CASH'), 'INCOMPLETE_RESEARCH')
        raw_input = self.input_reader(snapshot)
        require(type(raw_input) is bytes and len(raw_input) <= 32*1024*1024
                and sha256(raw_input).hexdigest() == snapshot['input_sha256'], 'INPUT_BYTES_MISMATCH')
        args = json.loads(raw_input)['search_arguments']
        budget = exact(snapshot['available_cash_exact'])
        identity = {k: exact(v) for k,v in snapshot['budget_identity_exact'].items()}
        require(budget > 0 and budget == exact(snapshot['investable_equity_exact']) == identity['entered_cash']
                and identity['fees'] == 0 and identity['residual_cash'] >= 0
                and identity['stock_notional'] + identity['residual_cash'] == budget, 'CASH_ONLY_IDENTITY')
        stocks = snapshot['stocks']; targets = snapshot['target_quantities']
        require(isinstance(stocks, list) and len({s['security_id'] for s in stocks}) == len(stocks)
                and len({s['ticker'] for s in stocks}) == len(stocks)
                and set(targets) == {s['security_id'] for s in stocks}
                and bool(stocks) == (snapshot['status'] == 'AVAILABLE'), 'SELECTED_DOMAIN_MISMATCH')
        allocations = {}
        for stock in stocks:
            sid = stock['security_id']; q = targets[sid]
            require(type(q) is int and q > 0 and type(stock['units']) is int and stock['units'] == q
                    and args['metadata'][sid]['ticker'] == stock['ticker'], 'TARGET_IDENTITY_MISMATCH')
            price = exact(args['prices'][sid]); require(price > 0, 'INVALID_SAVED_BUDGET_PRICE')
            allocations[sid] = q * price
        require(sum(allocations.values(), Fraction()) == identity['stock_notional'], 'ALLOCATION_MISMATCH')
        rows = []; used = []
        for stock in stocks:
            sid = stock['security_id']; allocation = allocations[sid]
            row = dict(security_id=sid, ticker=stock['ticker'], target_quantity=targets[sid],
                       allocation_cash=str(allocation), quantity=0, limit_price=None, notional='0',
                       status='UNAVAILABLE', refresh_by=None)
            try:
                now = self.clock(); require(now.tzinfo is not None, 'AWARE_CLOCK_REQUIRED')
                session = now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
                pack = self.identity_reader(snapshot, deepcopy(stock), session)
                files, pins = pack['files'], pack['source_hashes']
                require(isinstance(files, dict) and 0 < len(files) <= 1000 and set(files) == set(pins), 'IDENTITY_EVIDENCE_REQUIRED')
                require(all(type(v) is bytes for v in files.values()) and sum(len(v) for v in files.values()) <= 128*1024*1024, 'IDENTITY_EVIDENCE_TOO_LARGE')
                for name, raw in files.items():
                    require(sha256(raw).hexdigest() == pins[name] == snapshot['sources'].get(name), 'IDENTITY_SOURCE_CHANGED')
                document = files[pack['manifest_path']]
                manifest = json.loads(document)
                candidates = [c for c in manifest['candidates'] if c['security_id'] == sid]
                require(len(candidates) == 1, 'CURRENT_IDENTITY_UNAVAILABLE')
                candidate = candidates[0]
                require(candidate['ticker'] == stock['ticker'] and candidate['issuer_id'] == args['metadata'][sid]['issuer_id']
                        and candidate['status'] == 'READY_CONDITIONAL' and candidate['identity_reviewed'] is True
                        and candidate['coordinate_reviewed'] is True
                        and candidate['identity_source_references']
                        and all(ref in pins for ref in candidate['identity_source_references']), 'CURRENT_COORDINATE_UNAVAILABLE')
                require(not any(e['date'] > snapshot['as_of'] for e in candidate.get('true_share_events', [])), 'KNOWN_UNIT_EVENT')
                quote = self.quote_reader(deepcopy(stock)); raw = quote['raw']
                require(type(raw) is bytes and len(raw) <= 4*1024*1024, 'RAW_QUOTE_REQUIRED')
                parsed = json.loads(raw)
                current = parsed['chart']['result'][0]
                require(current['meta'].get('instrumentType') == 'EQUITY', 'EQUITY_QUOTE_REQUIRED')
                for kind, events in current.get('events', {}).items():
                    if kind == 'dividends': continue
                    require(not events, 'UNPROCESSED_CURRENT_UNIT_OR_IDENTITY_EVENT')
                checked = self.clock()
                decoded = decode_intraday_reference(raw, ticker=stock['ticker'], now=checked, captured_at=quote['captured_at'])
                require(decoded['session'] == session and checked < datetime.fromisoformat(decoded['refresh_by']), 'REFERENCE_EXPIRED')
                limit = exact(decoded['observed_cap']); quantity = min(targets[sid], int(allocation // limit))
                row.update(decoded, status='AVAILABLE' if quantity else 'WAIT_CASH', quantity=quantity,
                           limit_price=decoded['observed_cap'] if quantity else None,
                           notional=str(quantity*limit), quote_sha256=sha256(raw).hexdigest(),
                           identity_document_sha256=sha256(document).hexdigest(), source_hashes=deepcopy(pins),
                           checked_at=checked.isoformat(), captured_at=quote['captured_at'].isoformat())
                used.append((row, raw, quote['captured_at']))
            except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as error:
                row['reason'] = str(error)
            rows.append(row)
        # Slow later securities must never leave an expired first-security price visible.
        final_now = self.clock()
        for row, raw, captured in used:
            try:
                decode_intraday_reference(raw, ticker=row['ticker'], now=final_now, captured_at=captured)
                require(final_now < datetime.fromisoformat(row['refresh_by']), 'REFERENCE_EXPIRED')
            except (ValueError, KeyError, TypeError, ArithmeticError) as error:
                for key in ('last_price','minute_low','observed_cap'):
                    row.pop(key, None)
                row.update(status='UNAVAILABLE', quantity=0, limit_price=None, notional='0', refresh_by=None, reason=str(error))
        require(self.snapshot_reader(research_id) == snapshot, 'SNAPSHOT_CHANGED_DURING_REFERENCE')
        reserved = sum((exact(row['notional']) for row in rows), Fraction())
        require(0 <= reserved <= identity['stock_notional'] <= budget, 'REFERENCE_BUDGET_EXCEEDED')
        available = sum(row['status'] == 'AVAILABLE' for row in rows)
        return dict(research_id=research_id, research_version=VERSION,
                    status=('ALL_CASH' if not rows else 'AVAILABLE' if available == len(rows) else 'PARTIAL' if available else 'UNAVAILABLE'),
                    stocks=rows, available_cash=str(budget), indicative_notional=str(reserved),
                    remaining_cash=str(budget-reserved), research_only=True, execution_blocked=True, orders_created=False,
                    source_authenticated=False, historical_target_units_certified=False,
                    fee_scope='COMMISSION_ZERO_OTHER_FEES_UNKNOWN_NOT_RESERVED',
                    pricing_policy='FRESH_LAST_COMPLETED_MINUTE_MIN_FLOOR_CENT_NO_AUTOMATIC_ORDER_REPRICING',
                    notes=['宁可未成交，不自动追价；报价失效停止参考。',
                           '逐股额度来自封存研究资金分配；目标数量为条件上限，不是实际账户差额单。',
                           '每次参考可随新行情改变；不会同步修改券商订单，尚未验证收益改善。'])
