"""Add exactly three evidenced events; preserve all historical guards privately."""
import hashlib,json
from pathlib import Path
from types import FunctionType,SimpleNamespace
from backtest import ndx_current_receipt_quote_guard_research as previous
from scripts import ndx_current_three_split_fact_readback_20260919 as facts

SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
FACT_SOURCE=Path(facts.__file__).resolve();FACT_LOADED=hashlib.sha256(FACT_SOURCE.read_bytes()).hexdigest()
FACT=previous.BASE/'current_mstr_pdf_split_20260919_v1/three_split_facts.json'
FACT_SHA='e02e164554cb56f2aaed60b89e8adc3f059144bb350e88d7206e2fe74dbd401c'
ADDITIONAL_BLOCKED=frozenset({'TRI','WDC'})


def load_registry():
    old=previous.gap.load_registry();expected=dict(old['historical_expected_source_hashes'])
    previous.gap.merge(expected,{str(SOURCE):LOADED,str(FACT):FACT_SHA,str(FACT_SOURCE):FACT_LOADED})
    if hashlib.sha256(FACT.read_bytes()).hexdigest()!=FACT_SHA:raise ValueError('Hard three event facts differ')
    saved=json.loads(FACT.read_bytes())
    if facts.build()!=saved:raise ValueError('Three primary facts do not reproduce original bytes')
    previous.gap.merge(expected,saved['source_hashes'])
    rows=[dict(r) for r in old['events']]
    prescribed={'MSTR':('2024-08-08',10),'SHOP':('2022-06-29',10),'WMT':('2024-02-26',3)}
    if len(saved['events'])!=3 or {r['ticker'] for r in saved['events']}!=set(prescribed):raise ValueError('Exact three event set required')
    for fact in saved['events']:
        if (fact['first_adjusted_trading_date'],fact['new_shares'])!=prescribed[fact['ticker']] or fact['old_shares']!=1 or fact['specific_simple_share_split_event_supported'] is not True:raise ValueError('Exact new event coordinate differs')
        rows.append(dict(fact,simple_split_guard_eligible=True))
    if len(rows)!=28 or len({(r['ticker'],r['first_adjusted_trading_date']) for r in rows})!=28:raise ValueError('Exact 28 unique events required')
    eligible=sum(r['simple_split_guard_eligible'] for r in rows)
    if eligible!=26:raise ValueError('Exact 26 eligible events required')
    output=dict(old,events=rows,event_count=28,guard_eligible_event_count=26,schema='SPECIFIC_28_EVENT_EXACT_GAP_REGISTRY_V1',additional_complex_tickers_blocked=sorted(ADDITIONAL_BLOCKED))
    return previous.gap.attach_partition(output,expected,previous.gap.partition(expected,previous.gap.drift.load_contract(),require_all=True))


def reconstruct_current_receipt_quote(**arguments):
    registry_proxy=SimpleNamespace(**dict(vars(previous.gap.original),BLOCKED=previous.gap.original.BLOCKED|ADDITIONAL_BLOCKED))
    gap_proxy=SimpleNamespace(**dict(vars(previous.gap),load_registry=load_registry,original=registry_proxy))
    loaded=dict(previous.LOADED);previous.gap.merge(loaded,{str(SOURCE):LOADED})
    function=previous.reconstruct_current_receipt_quote
    private=FunctionType(function.__code__,dict(function.__globals__,gap=gap_proxy,LOADED=loaded),function.__name__,function.__defaults__,function.__closure__)
    result=private(**arguments)
    result.update(schema='CURRENT_RECEIPT_28_SPECIFIC_EVENT_QUOTE_GUARD_V1',registry_event_count=28,registry_guard_eligible_event_count=26,additional_complex_tickers_blocked=sorted(ADDITIONAL_BLOCKED))
    return result
