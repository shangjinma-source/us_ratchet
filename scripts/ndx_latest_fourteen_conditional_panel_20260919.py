"""Append five dated assumptions; preserve every cell and assumption of the nine panel."""
import argparse
import copy
import json
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ndx_latest_conditional_panel_20260919 as old
from scripts import ndx_five_additional_conditional_identities_20260919 as five

CORE_SHA = old.CORE_SHA
PANEL = dict(path=str(old.BASE/'latest_conditional_panel_20260919_v1/panel.json'), sha256='06f917bcdf67a92bc0135ce7c1a5ac28e5ad8bac15823ed85968bfe744811ec0')
FIVE = dict(path=str(old.BASE/'five_additional_conditional_identities_20260919_v1/identities.json'), sha256='aa8a2e5a68b538de97f22ed9ab849cac840043c1c5f9ec0c333786110d1d52d4')
AUDIT = dict(path=str(old.BASE/'latest_conditional_panel_20260919_v1/independent_readback.json'),sha256='fe2742de54d20602045a55a80b196c0961b40af846993c7a471c66b318373a2e')
ADDED = {'FAST','ODFL','DXCM','LRCX','AMZN'}
LOADED = {str(Path(m.__file__).resolve()):old.archive.drift.file_sha(m.__file__) for m in (old,five)}
LOADED[str(Path(__file__).resolve())] = old.archive.drift.file_sha(__file__)


def coordinate(fact, calendar):
    ticker = fact['ticker']
    if ticker not in ADDED or any(fact[k] is not False for k in five.FALSE):
        raise ValueError('Exact conditional five facts required')
    floor = fact['minimum_conditional_date']
    if ticker == 'LRCX' and (floor != '2024-10-03' or calendar[0] < floor or fact['cusip'] != '512807306' or fact['old_cusip_not_joined'] != '512807108'):
        raise ValueError('Post-transition LRCX window required')
    # A cover period is a dated fact anchor, NEVER its publication/availability date.
    period = ' '.join(fact['original_cover_fields']['dei:documentperiodenddate']['original_text'].split()).replace(' ,', ',')
    anchor = datetime.strptime(period, '%B %d, %Y').date().isoformat()
    fields = dict(ticker=ticker, security_id=fact['conditional_research_security_id'], issuer_id=fact['issuer_id'],
        cusip=fact['cusip'], security_class=fact['security_class'])
    return dict(**fields, scope=old.core.SCOPE, latest_interval_verified=False, provider_binding_verified=False,
        assumed_window=dict(first=calendar[0], last=calendar[-1]),
        dated_fact=dict(**fields, dated_as_of=anchor, source_references=[FIVE]))


def prove_old_subset(before, after):
    for name in ('returns','nominal_close','raw_volume','dollar_volume'):
        if not before[name].equals(after[name][before[name].columns]):
            raise ValueError('Original nine typed numeric cells changed')
    rows = {r['ticker']:r for r in after['observed_provenance_and_missing']}
    for row in before['observed_provenance_and_missing']:
        if row['ticker'] not in ADDED and not old.batch.exact(row,rows[row['ticker']]):
            raise ValueError('Original unchanged provenance row changed')
    expected = before['universe'].to_dict('records')
    actual = after['universe'][after['universe'].ticker.isin(old.TICKERS)].to_dict('records')
    if not old.batch.exact(expected, actual):raise ValueError('Original nine security/risk rows changed')


def prove_old_supplemental(before, after):
    if set(before)!=old.TICKERS or not set(before)<=set(after):raise ValueError('Original nine supplemental denominator differs')
    for ticker,value in before.items():
        if not old.batch.exact(value,after[ticker]):raise ValueError('Original nine full supplemental dates/risk provenance changed')


def build():
    sources = dict(LOADED)
    original = old.batch.read(PANEL,sources); old.verify(original)
    audit=old.batch.read(AUDIT,sources)
    if audit['schema']!='LATEST_CONDITIONAL_PANEL_INDEPENDENT_READBACK_V1' or not old.batch.exact(audit['panel_reference'],PANEL):raise ValueError('Original nine independent audit link differs')
    if any(audit[k] is not False for k in ('raw_oracle_repeated','producer_assemble_called','fitter_called','point_in_time_verified','legal_training_input_admitted','promotion_allowed')):raise ValueError('Original independent audit scope differs')
    details=audit['details']
    for k,v in dict(observed_rows=101,numeric_channels=96,conditional_securities=9,returns_cells=1134,nominal_close_cells=1143,volume_cells=567,dollar_volume_cells=567).items():
        if type(details[k]) is not int or details[k]!=v:raise ValueError('Original nine audit denominator differs')
    if any(details[k] is not True for k in ('all_four_numeric_frames_reconstructed','universe_and_all_101_gap_rows_reconstructed','rangeindex_and_panel_checksum_verified','distinct_dates_and_original_facts_verified')):raise ValueError('Complete old independent audit required')
    old.archive.merge(sources,audit['historical_expected_source_hashes'])
    if not old.batch.exact(old.archive.verify_expected_sources(audit['historical_expected_source_hashes'],old.archive.load_contract()),audit['archive_resolution']):raise ValueError('Original audit archive partition differs')
    facts = old.batch.read(FIVE,sources)
    if not old.batch.exact(facts,five.build()):raise ValueError('Five raw document relationships differ')
    old.archive.merge(sources,original['historical_expected_source_hashes']);old.archive.merge(sources,facts['source_hashes'])
    before = old.typed_decode(original['panel'])
    calendar = [d.date().isoformat() for d in before['nominal_close'].index]
    docs = {key:old.batch.read(old.reference(key),sources) for key in ('plan','index','fifteen')}
    channels = {}
    for entry, task in zip(docs['index']['entries'],docs['plan']['tasks']):
        value = old.batch.read(dict(path=entry['path'],sha256=entry['sha256']),sources)
        old.batch.validate_wrapper(value,task,old.ANCHORS['plan'][1])
        if task['mode'] != 'BLOCKED':channels[task['ticker']] = value['result']
    provenance = before['observed_provenance_and_missing']
    assertions = {r['ticker']:copy.deepcopy(r['channel_audit_assertion']) for r in provenance if r['channel_audit_assertion'] is not None}
    coordinates = {r['ticker']:copy.deepcopy(r['coordinate_assumption']) for r in provenance if r['coordinate_assumption'] is not None}
    risks = {r['ticker']:copy.deepcopy(r['risk_assumption']) for r in provenance if r['risk_assumption'] is not None}
    supplemental = copy.deepcopy(original['supplemental_dated_and_risk_provenance'])
    if {r['ticker'] for r in facts['rows']} != ADDED or len(facts['rows']) != 5:raise ValueError('Complete five denominator required')
    for fact in facts['rows']:
        ticker=fact['ticker']; proposal,=[r for r in docs['fifteen']['rows'] if r['ticker']==ticker]
        coordinates[ticker]=coordinate(fact,calendar)
        risks[ticker]=dict(scope=old.core.SCOPE, latest_interval_verified=False, continued_historical_label_is_explicit_assumption=True,
            historical_labels=[proposal['risk_chain_candidate']],risk_chain=proposal['risk_chain_candidate'],source_kind=proposal['risk_source_kind'],source_references=[old.reference('fifteen')])
        supplemental[ticker]=old.supplemental_provenance(fact,coordinates[ticker],proposal,fact['original_cover_fields']['dei:documentperiodenddate'])
        supplemental[ticker]['selected_anchor_kind']='COVER_PERIOD_END_NOT_PUBLICATION_OR_JOINT_AVAILABILITY'
    panel=old.core.assemble_conditional_panel(observed_rows=[dict(ticker=r['ticker'],issuer_id=r['observed_issuer_id']) for r in provenance],
        calendar=calendar,cutoff=before['cutoff'],channels=channels,channel_audits=assertions,coordinate_assumptions=coordinates,risk_assumptions=risks)
    if set(panel['returns'].columns)!=old.TICKERS|ADDED or panel['conditional_security_count']!=14:raise ValueError('Exact fourteen supported channels required')
    prove_old_subset(before,panel)
    prove_old_supplemental(original['supplemental_dated_and_risk_provenance'],supplemental)
    encoded=old.typed_encode(panel);decoded=old.typed_decode(encoded)
    old.core.selected_mapping(decoded,decoded['universe'].security_id.tolist())
    return dict(schema='SOURCE_BOUND_LATEST_FOURTEEN_CONDITIONAL_PANEL_V1',panel=encoded,
        original_nine_reference=PANEL,old9_audit_reference=AUDIT,five_identity_reference=FIVE,supplemental_dated_and_risk_provenance=supplemental,
        original_nine_numeric_cells_and_assumptions_exact=True,previous_fit_results_reused=False,
        subset_selection_basis='DATED_COORDINATE_AND_DECLARED_RISK_AND_LIQUIDITY_EVIDENCE_NOT_RETURN_RANKING',
        historical_expected_source_hashes=sources,archive_resolution=old.archive.verify_expected_sources(sources,old.archive.load_contract()),
        **{k:False for k in ('target_cardinality_fixed','source_point_in_time_verified','legal_training_input_admitted','historical_six_input_training_ready','fit_performed','execution_authorized','winner_selected','promotion_allowed')})


def verify(value):
    if not old.batch.exact(value,build()):raise ValueError('Fourteen source-bound panel does not reproduce exactly')


def publish_verified(path,value):
    verify(value);saved=old.batch.recipe.exclusive_publish(path,value);verify(value);return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    print(json.dumps(publish_verified(args.output,build())))
