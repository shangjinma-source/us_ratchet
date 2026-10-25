"""Assemble fixed-source real January OHLC; no search or economic execution."""
import csv
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backtest.return_priority_monthly_execution_inputs import BASIS
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4
from backtest.continuous_guided_account_decision import REQUIRED_PINS

OUT = ROOT/'tmp/qqq_20201231_anchor_20261025'
START, END = '2021-12-31', '2022-01-31'


def prepare():
    hashes = {}
    def read(path):
        content = path.read_bytes()
        hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(content).hexdigest()
        return content
    training = json.loads(read(OUT/'january2022_training_diagnostic.json'))
    if training['status']!='REAL_TRAINING_INPUT_COMPILED_CONDITIONALLY':
        raise ValueError('TRAINING_NOT_COMPILED')
    arguments = training['compiled_search_arguments']
    reference = json.loads(read(ROOT/'tmp/free_history_price_probe_20261025_v1/AAPL.response'))
    sessions = [datetime.fromtimestamp(t,timezone.utc).date().isoformat() for t in reference['chart']['result'][0]['timestamp']]
    sessions = [day for day in sessions if START<=day<=END]
    if sessions[0]!=START or sessions[-1]!=END:
        raise ValueError('EXECUTION_CALENDAR_BOUNDARY_MISSING')
    ohlc, provenance, source_reviews = {}, {}, []
    event_inventory, action_unknown = [], []
    coordinates = {row['ticker']:row for row in training['unit_diagnostics']}
    for candidate in training['window']['candidates']:
        ticker,sid,source = candidate['ticker'],candidate['security_id'],candidate['training_source']
        content = read(ROOT/source)
        if hashes[source]!=training['source_hashes'][source]:
            raise ValueError('TRAINING_EXECUTION_SOURCE_CHANGED:'+ticker)
        rows = {}
        events = None
        if source.endswith('.response'):
            result = json.loads(content)['chart']['result'][0]
            quote = result['indicators']['quote'][0]
            events = result.get('events',{})
            for index,stamp in enumerate(result['timestamp']):
                day = datetime.fromtimestamp(stamp,timezone.utc).date().isoformat()
                if START<=day<=END:
                    rows[day] = {key:quote[key][index] for key in ('open','high','low','close')}
        else:
            for row in csv.DictReader(content.decode('utf-8-sig').splitlines()):
                day = row.get('date',row.get('Date'))
                if day[4:5]!='-':
                    day = datetime.strptime(day,'%d-%m-%Y').date().isoformat()
                if START<=day<=END:
                    rows[day] = {key:row.get(key,row.get(key.capitalize())) for key in ('open','high','low','close')}
        factor = Fraction(coordinates[ticker]['post_cutoff_constant_factor'])
        restored = {}
        for day in sessions:
            if day not in rows:
                raise ValueError('MISSING_EXECUTION_SESSION:'+ticker+':'+day)
            raw_bar = {key:Fraction(str(value)) for key,value in rows[day].items()}
            bar = {key:value*factor for key,value in raw_bar.items()}
            if min(bar.values())<=0 or not bar['low']<=min(bar['open'],bar['close'])<=max(bar['open'],bar['close'])<=bar['high']:
                raise ValueError('INVALID_RESTORED_OHLC:'+ticker+':'+day)
            restored[day] = {key:str(value) for key,value in bar.items()}
        if Fraction(restored[START]['close'])!=Fraction(candidate['decision_cost']):
            raise ValueError('DECISION_COST_SCALE_MISMATCH:'+ticker)
        ohlc[sid] = restored
        provenance[sid] = dict(price_basis=BASIS,whole_source=source)
        if events is None:
            action_unknown.append(ticker)
        else:
            for kind,records in events.items():
                for event in records.values():
                    day = datetime.fromtimestamp(event['date'],timezone.utc).date().isoformat()
                    if START<day<=END:
                        event_inventory.append(dict(ticker=ticker,security_id=sid,date=day,kind=kind,
                            provider_event=event,source=source,execution_coordinate_factor=str(factor),
                            economic_action_admitted=False))
        source_reviews.append(dict(ticker=ticker,security_id=sid,source=source,scale=str(factor),
            restored_ohlc_rows=len(restored),decision_cost_equals_restored_close=True,
            provider_action_stream_available=events is not None,
            later_constant_is_not_a_holding_action=True))
    for path in ('backtest/return_priority_fresh_cash_quantity_search.py',
                 'backtest/return_priority_monthly_execution_inputs.py',
                 'backtest/return_priority_monthly_execution_inputs_v4.py',
                 'backtest/historical_dividend_frontier_research.py',
                 'backtest/historical_dividend_next_open_book_research.py',
                 'backtest/capped_frontier_rerank_research.py',
                 'scripts/audit_capped_training_frontier.py',
                 *REQUIRED_PINS):
        read(ROOT/path)
    pins = {**training['source_hashes'],**hashes}
    non_dividends = [event for event in event_inventory if event['kind']!='dividends']
    blockers = []
    if non_dividends:
        blockers.append('OBSERVED_JANUARY_NON_DIVIDEND_ACTIONS_REQUIRE_EVENT_MAPPING')
    if action_unknown:
        blockers.append('FIXED_CSV_SOURCES_HAVE_NO_ACTION_STREAM:'+','.join(action_unknown))
    if any(event['kind']=='dividends' for event in event_inventory):
        blockers.append('OBSERVED_DIVIDEND_AMOUNTS_UNITS_AND_PAYMENT_STATUS_REQUIRE_MAPPING')
    prepared = dict(session_dates=sessions,source_hashes=pins,metadata=arguments['metadata'],
        source_provenance=provenance,ohlc=ohlc,
        windows=[dict(decision_date=START,active_date=sessions[1],search_arguments=arguments)],
        split_events_reference_only=[],identity_migrations=[],cash_stock_merger_events=[],fractional_settlements={},
        distribution_events=[],distribution_fractional_cash_values={},supported_conversions=[],unsupported_conversions=[])
    # Schema assembly is safe without running the economic book. Empty action
    # arrays here are unresolved placeholders, explicitly guarded by blockers.
    assembled = assemble_monthly_execution_inputs_v4(prepared)
    return dict(status='REAL_OHLC_AND_ASSEMBLY_READY_ACTION_REVIEW_PENDING' if blockers else 'REAL_EXECUTION_INPUTS_CONDITIONAL',
        prepared=prepared,assembled=assembled,ohlc=ohlc,source_reviews=source_reviews,
        provider_event_inventory=event_inventory,action_stream_missing=action_unknown,
        execution_blockers=blockers,runner_execution_authorized=not blockers,
        dividend_events=None,source_hashes=pins,search_calls=0,economic_run_completed=False,
        terminal_date=END,terminal_creates_new_decision=False,
        limitations=['Provider event absence is conditional third-party evidence, not an exhaustive official corporate-action audit.',
                    'Cash dividend units are not silently multiplied by price-coordinate factors.',
                    'Unmapped actions and dividends prevent economic execution even though assembly succeeds.'])


if __name__=='__main__':
    result=prepare()
    (OUT/'january2022_execution_diagnostic.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=result['status'],securities=len(result['ohlc']),sessions=len(result['assembled']['session_dates']),
        observed_events=result['provider_event_inventory'],blockers=result['execution_blockers']),ensure_ascii=False))
