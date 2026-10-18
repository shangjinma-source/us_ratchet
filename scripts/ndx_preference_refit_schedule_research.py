"""Prepare all fifteen USER_PREFERENCE research decisions; no portfolio selection.

Training calendars are independently compared with frozen QQQ/SPY observations.
These retrospective observations do not authenticate historical PIT or prices.
"""
import argparse
import csv
import hashlib
import io
import json
import logging
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_dynamic_refit_schedule_research as schedule_module
from backtest.ndx_dynamic_training_semantics import training_semantics
from scripts import ndx_equal_weight_base_inputs as equal_inputs

INVENTORY = ROOT / 'data/cache/research/dynamic_fractional_frontiers_v1/inventory_20260912.json'
INVENTORY_SHA = '8ec2ab2d22c2441190606f301e62380c93345a7c66f9ad8987c3dd229eee124d'
CALENDAR_MANIFEST = ROOT / ('data/cache/research/ndx_observed_us_session_calendar_v2/source_snapshots/'
    'eb1c91146fcc33bac61d999e8db18b8bb7747cbe89757e4f83d17aa5d3dc7040/manifest.json')
CALENDAR_SHA = '4b3a74324247d6f3aee74999e5d5a3ae97b448943821b96d814f385e62dc691b'
PREFERENCE = ('AMAT', 'AVGO', 'CDNS', 'GOOG')
COORDINATE_KEYS = ('source_batch', 'universe_track', 'selection_date')
PARAMETERS = ('fit_days', 'shrinkage_intensity', 'turnover_anchor_strength', 'max_single_weight',
              'min_single_weight', 'top_weight_cap', 'minimum_effective_n_ratio', 'risk_chain_top1_cap')
SELF = Path(__file__).resolve()
LOADED = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in
          (SELF, Path(schedule_module.__file__).resolve(), Path(equal_inputs.__file__).resolve(),
           ROOT / 'backtest/ndx_dynamic_training_semantics.py')}


def _read(path, expected):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Preference input SHA differs: ' + str(path))
    return raw


def _validate_inventory(inventory):
    if (inventory['date_count'] != 15 or len(inventory['reports']) != 15
            or inventory['record_count'] != 351255
            or any(inventory[name] is not False for name in
                   ('execution_performed', 'point_in_time_verified', 'promotion_allowed',
                    'cross_date_global_ranking_performed'))):
        raise ValueError('Complete fifteen-date research inventory required')
    coordinates = [tuple(row['coordinate'][key] for key in COORDINATE_KEYS) for row in inventory['reports']]
    dates = [row['coordinate']['selection_date'] for row in inventory['reports']]
    if len(set(coordinates)) != 15 or dates != sorted(set(dates)):
        raise ValueError('Unique ordered inventory dates required')
    if sum(row['counts']['expected_task_count'] for row in inventory['reports']) != 351255:
        raise ValueError('Inventory task denominator differs')


def _preference_decision(*, descriptor, report, prepared):
    analysis = report['analysis']
    expected = analysis['expected_date']
    coordinate = descriptor['coordinate']
    if (report['schema'] != 'ndx_combined_fractional_frontier_report_v1'
            or any(expected[key] != coordinate[key] for key in COORDINATE_KEYS)
            or analysis['counts'] != descriptor['counts']
            or any(report[key] is not False for key in ('training_rerun', 'cutoff_refit_performed',
                'execution_performed', 'point_in_time_verified', 'promotion_allowed'))
            or analysis['technology_scope_status'] != 'UNRESOLVED_CURRENT_PURE_TECH_DEFINITION'):
        raise ValueError('Bound frontier research coordinate differs')
    references = analysis['user_preference_references']
    if len(references) != 1 or analysis['counts']['user_preference_count'] != 1:
        raise ValueError('Exactly one USER_PREFERENCE reference required')
    reference = references[0]
    if (reference['tickers'] != ';'.join(PREFERENCE) or reference['weight_spec'] != 'equal_weight'
            or reference['holding_count'] != 4 or reference['origin'] != 'EQUAL_WEIGHT_BASE'
            or reference['user_preference_reference'] is not True
            or reference['technology_scope_passed'] is not None):
        raise ValueError('USER_PREFERENCE identity or unknown scope differs')
    inputs = prepared['inputs']
    semantics = training_semantics(inputs=inputs, decision_data_end=expected['decision_data_end'],
        source_batch=coordinate['source_batch'], universe_track=coordinate['universe_track'])
    if (semantics != prepared['training_semantics']
            or semantics['training_semantics_sha256'] != expected['training_semantics_sha256']
            or prepared['summary']['all_base_count'] + prepared['summary']['delta_count'] != expected['expected_task_count']
            or PREFERENCE not in prepared['combinations']):
        raise ValueError('Original training semantics or complete base denominator differs')
    identity = dict(schema_version='ndx_equal_base_combined_task_v1', **coordinate,
        decision_data_end=expected['decision_data_end'],
        training_semantics_sha256=expected['training_semantics_sha256'],
        tickers=';'.join(PREFERENCE), holding_count=4, weight_spec='equal_weight')
    job_id = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if reference['job_id'] != job_id:
        raise ValueError('Preference job identity differs from restored base definition')
    universe = inputs['universe']
    names = universe.loc[universe['ticker'].isin(PREFERENCE)]
    if (len(names) != 4 or set(names['ticker']) != set(PREFERENCE)
            or names['security_id'].duplicated().any() or names['issuer_id'].duplicated().any()):
        raise ValueError('Unique original preference SID and issuer mapping required')
    selected = {row['security_id']: {key: row[key] for key in ('ticker', 'issuer_id', 'risk_chain')}
                for row in names.to_dict('records')}
    period = dict(decision_date=expected['decision_data_end'], execution_date=coordinate['selection_date'],
        cutoff=expected['decision_data_end'], returns=inputs['returns'], selected=selected,
        weight_spec='equal_weight', parameters={key: inputs['contract'][key] for key in PARAMETERS},
        source_hashes=schedule_module._merge(report['source_hashes'], prepared['source_hashes'], LOADED,
            {str(Path(descriptor['path']).resolve()): descriptor['sha256']}))
    audit = dict(coordinate=coordinate, job_id=job_id,
        training_semantics_sha256=semantics['training_semantics_sha256'],
        training_cutoff=expected['decision_data_end'], reference=reference,
        actual_original_parameters=period['parameters'], selected_identity=selected,
        source_report_path=descriptor['path'], source_report_sha256=descriptor['sha256'])
    return period, audit


def _observed_dates(raw):
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    if (not rows or len(rows[0]) != len(set(rows[0])) or 'Date' not in rows[0]
            or any(len(row) != len(rows[0]) for row in rows[1:])):
        raise ValueError('Canonical observed calendar CSV required')
    position = rows[0].index('Date')
    dates = [schedule_module._day(row[position]) for row in rows[1:]]
    if not dates or dates != sorted(set(dates)):
        raise ValueError('Unique ordered observed sessions required')
    return dates


def _build_calendar(decisions, observed_by_ticker):
    if set(observed_by_ticker) != {'QQQ', 'SPY'}:
        raise ValueError('Two independent observed ETF date channels required')
    start, last_cutoff, end = (decisions[0]['decision_date'], decisions[-1]['cutoff'],
                             decisions[-1]['execution_date'])
    channels = [[day for day in observed_by_ticker[ticker] if start <= day <= end] for ticker in ('QQQ', 'SPY')]
    if not channels[0] or channels[0] != channels[1] or channels[0][0] != start or channels[0][-1] != end:
        raise ValueError('Observed ETF calendar disagreement or missing boundary')
    training_union = sorted({day.date().isoformat() for period in decisions for day in period['returns'].index
                             if start <= day.date().isoformat() <= last_cutoff})
    if training_union != [day for day in channels[0] if day <= last_cutoff]:
        raise ValueError('Training session union differs from frozen observed sessions')
    positions = {day: index for index, day in enumerate(channels[0])}
    for period in decisions:
        if (period['decision_date'] not in positions or period['execution_date'] not in positions
                or positions[period['execution_date']] != positions[period['decision_date']] + 1):
            raise ValueError('Preference execution is not next observed session')
    return channels[0], dict(training_union_session_count=len(training_union),
        observed_tail_sessions=[day for day in channels[0] if day > last_cutoff],
        observed_channels=['QQQ', 'SPY'], session_count=len(channels[0]),
        scope='TRAINING_UNION_CROSSCHECKED_WITH_FROZEN_ETF_DATES_PLUS_OBSERVED_EXECUTION_TAIL',
        business_day_inference_used=False, point_in_time_verified=False,
        exchange_calendar_completeness_verified=False, price_identity_binding_verified=False)


def prepare_reference_schedule():
    schedule_module._verify(LOADED)
    inventory = json.loads(_read(INVENTORY, INVENTORY_SHA))
    _validate_inventory(inventory)
    manifest = json.loads(_read(CALENDAR_MANIFEST, CALENDAR_SHA))
    calendar_sources = {str(CALENDAR_MANIFEST): CALENDAR_SHA}
    observed = {}
    for source in manifest['sources']:
        ticker = source['ticker']
        if ticker in observed or ticker not in ('QQQ', 'SPY'):
            raise ValueError('Unique frozen ETF calendar source required')
        path = Path(source['frozen_path']).resolve()
        if path.parent != CALENDAR_MANIFEST.parent:
            raise ValueError('Frozen calendar source outside snapshot')
        observed[ticker] = _observed_dates(_read(path, source['frozen_sha256']))
        calendar_sources[str(path)] = source['frozen_sha256']
    decisions, audits = [], []
    shared = schedule_module._merge(LOADED, calendar_sources, {str(INVENTORY): INVENTORY_SHA})
    for descriptor in inventory['reports']:
        coordinate = descriptor['coordinate']
        logging.info('Restoring USER_PREFERENCE %s', coordinate['selection_date'])
        report = json.loads(_read(descriptor['path'], descriptor['sha256']))
        schedule_module._verify(report['source_hashes'])
        prepared = equal_inputs.prepare_equal_base_date(**coordinate)
        decision, audit = _preference_decision(descriptor=descriptor, report=report, prepared=prepared)
        decision['source_hashes'] = schedule_module._merge(decision['source_hashes'], shared)
        decisions.append(decision)
        audits.append(audit)
    if len(decisions) != 15:
        raise ValueError('Entire fifteen-date reference path required')
    calendar, calendar_audit = _build_calendar(decisions, observed)
    result = schedule_module.build_refit_schedule_research(calendar=calendar, decisions=decisions)
    if result['decision_count'] != 15 or len(result['schedule']) != 15:
        raise ValueError('Reference schedule dropped a required decision')
    schedule_module._verify(result['source_hashes'])
    return dict(schema='ndx_preference_refit_schedule_research_v1',
        reference_role='USER_PREFERENCE_REFERENCE', selection_policy='FIXED_USER_REFERENCE_NOT_WINNER_SELECTION',
        technology_scope_status='UNRESOLVED_CURRENT_PURE_TECH_DEFINITION',
        inventory_sha256=INVENTORY_SHA, date_count=15, source_batches=sorted({
            row['coordinate']['source_batch'] for row in audits}),
        reference_audit_by_date=audits, calendar_audit=calendar_audit,
        schedule_result=result, source_hashes=result['source_hashes'],
        training_battery_rerun=False, cutoff_refit_performed=True,
        execution_performed=False, price_identity_binding_verified=False,
        source_authenticity_verified=False, point_in_time_verified=False,
        unique_selection_performed=False, migration_control=False,
        promotion_allowed=False, review_status='DRAFT_PENDING_ROOT_REVIEW')


def save_new(report, path):
    path = Path(path).resolve()
    if (ROOT / 'data/cache/research').resolve() not in path.parents:
        raise ValueError('Separate research output required')
    schedule_module._verify(report['source_hashes'])
    encoded = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(encoded)
    if path.read_bytes() != encoded:
        raise ValueError('Reference schedule readback differs')
    schedule_module._verify(report['source_hashes'])
    return hashlib.sha256(encoded).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    report = prepare_reference_schedule()
    logging.info('Prepared full reference schedule dates=%d sessions=%d', report['date_count'],
                 report['calendar_audit']['session_count'])
    logging.info('Saved %s SHA256=%s', arguments.output, save_new(report, arguments.output))
