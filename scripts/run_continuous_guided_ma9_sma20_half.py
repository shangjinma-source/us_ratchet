"""Independent once-only two-scenario candidate. Sealed comparators are read-only."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
import re
from pathlib import Path
from unittest.mock import patch

from backtest.continuous_guided_cost_stress import SCENARIOS, prepare_arm
from backtest.continuous_guided_ma9_sma20_half_next_open import run_cost_ma9_sma20_half_next_open
from scripts.run_continuous_guided_cost_stress import prepare_run as prepare_sealed_inputs, canonical_hash, summarize
from scripts.compare_monthly_latched_exit import integer_text_limit

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = 'tmp/continuous_guided_ma9_sma20_half_20261019_v1'
CONTRACT = 'research_contracts/continuous_guided_ma9_sma20_half_execution_20261019_v1.json'
CONTRACT_SHA = 'cacd6e055725e5e26e4f6a35735c08961932d8464ac324f4e4eafdb829ab69bc'
APPROVAL = 'outputs/cost_stress_report_20261019_v1/approval.json'
APPROVAL_SHA = '1082938fef9c0237c6bf3a754078604e9b702150390caba15d451c8a6cf68619'
SEALED_RECEIPT_SHA = '5a4a519e32c6759e563e769c25ed1438f4f513946a449e17c5046ca99a58d15d'
ARM = 'continuous32_ma9_sma20_half'
REVIEW = 'tmp/ma9_sma20_half_independent_review_20261019_v1.json'
REVIEW_SHA = '6bed414d2ed7cc0141dc833c0076b371c67ca336e4025fc6be6965a160be1bd0'


def verify_pins(pins):
    for name, digest in pins.items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('SOURCE_DRIFT:' + name)


def prepare_run():
    prepared, assembled, resolver, sealed = prepare_sealed_inputs()
    if canonical_hash(sealed) != SEALED_RECEIPT_SHA:
        raise ValueError('SEALED_COST_INPUT_RECEIPT_CHANGED')
    pins = dict(sealed['source_hashes'])
    def read(name, digest):
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()): raise ValueError('OUTSIDE_ROOT')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest: raise ValueError('BINDING_HASH_MISMATCH:' + name)
        if name in pins and pins[name] != digest: raise ValueError('PIN_CONFLICT')
        pins[name] = digest
        return json.loads(raw)
    contract = read(CONTRACT, CONTRACT_SHA)
    if contract['scenarios'] != SCENARIOS or contract['initial_cash'] != '20000' or contract['candidate'] != ARM:
        raise ValueError('CONTRACT_PARAMETERS_CHANGED')
    proposal = read(contract['proposal']['path'], contract['proposal']['sha256'])
    if proposal['candidate'] != ARM: raise ValueError('PROPOSAL_CANDIDATE_MISMATCH')
    if REVIEW_SHA is None: raise ValueError('INDEPENDENT_REVIEW_HASH_NOT_PINNED')
    review = read(REVIEW, REVIEW_SHA)
    if review.get('status') != 'PASS_MA9_SMA20_KERNEL_AND_SYNTHETIC_BOOK': raise ValueError('INDEPENDENT_REVIEW_REQUIRED')
    for name, digest in review['source_hashes'].items():
        if name in pins and pins[name] != digest: raise ValueError('REVIEW_SOURCE_CONFLICT')
        pins[name] = digest
    approval = read(APPROVAL, APPROVAL_SHA)
    if approval['status'] != 'APPROVED_FOR_REPORT' or approval['receipt_sha256'] != SEALED_RECEIPT_SHA:
        raise ValueError('COMPARATOR_APPROVAL_REQUIRED')
    comparison = read(**dict(name=approval['comparison']['path'], digest=approval['comparison']['sha256']))
    top = read(approval['terminal']['path'], approval['terminal']['sha256'])
    if top['status'] != 'COMPLETE_PENDING_INDEPENDENT_REVIEW' or top['source_pins_unchanged'] is not True:
        raise ValueError('COMPARATORS_NOT_COMPLETE')
    for key, references in approval['arms'].items():
        values = {kind:read(ref['path'], ref['sha256']) for kind,ref in references.items() if kind != 'outcome'}
        # Authenticate large sealed outcomes without parsing or executing them.
        outcome = references['outcome']
        if outcome['path'] in pins and pins[outcome['path']] != outcome['sha256']:
            raise ValueError('COMPARATOR_OUTCOME_PIN_CONFLICT')
        pins[outcome['path']] = outcome['sha256']
        review = values['review']; ledger = values['ledger_review']
        if (review['status'] != 'SAVED_ARM_ARITHMETIC_REVIEWED' or
            review['cash_cost_review']['status'] != 'CASH_COST_BINDINGS_VERIFIED' or
            review['nav_review']['status'] != 'SAVED_STATE_NAV_AND_METRICS_VERIFIED' or
            review['outcome_sha256'] != outcome['sha256'] or
            review['metrics_sha256'] != references['metrics']['sha256'] or
            review['receipt_sha256'] != SEALED_RECEIPT_SHA or
            values['terminal']['status'] != 'COMPLETE' or
            values['terminal']['outcome_sha256'] != outcome['sha256'] or
            ledger['status'] != 'SUPPORTED_SAVED_LEDGER_REPLAY_VERIFIED' or
            ledger.get('whole_ledger_verified') is not True or
            ledger['source_hashes'].get(outcome['path']) != outcome['sha256']):
            raise ValueError('COMPARATOR_REVIEW_BINDING')
        if key != review['scenario'] + '__' + review['arm'] or values['metrics'] != comparison['arms'][review['scenario']][review['arm']]:
            raise ValueError('COMPARATOR_METRIC_BINDING')
    expected = {scenario+'__'+arm for scenario in SCENARIOS for arm in ('continuous32','continuous32_half')}
    if set(approval['arms']) != expected: raise ValueError('FOUR_SEALED_COMPARATORS_REQUIRED')
    for name in ('backtest/ma9_sma20_half.py',
                 'backtest/continuous_guided_ma9_sma20_half_next_open.py',
                 'scripts/run_continuous_guided_ma9_sma20_half.py'):
        digest = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        if name in pins and pins[name] != digest: raise ValueError('CANDIDATE_PIN_CONFLICT')
        pins[name] = digest
    evidence_path = 'tmp/six_arm_drawdown_attribution_20261019_v1/report.json'
    evidence = json.loads((ROOT/evidence_path).read_text(encoding='utf8'))
    pins[evidence_path] = hashlib.sha256((ROOT/evidence_path).read_bytes()).hexdigest()
    for name, digest in evidence['source_hashes'].items():
        if name in pins and pins[name] != digest: raise ValueError('EVIDENCE_PIN_CONFLICT')
        pins[name] = digest
    verify_pins(pins)
    bindings = [dict(arm=ARM, scenario=scenario, **SCENARIOS[scenario],
        assembled_sha256=canonical_hash(prepare_arm(assembled,scenario,pins))) for scenario in SCENARIOS]
    receipt = dict(schema='MA9_SMA20_HALF_RUN_RECEIPT_V1', status='PREFLIGHT_ONLY_NO_SEARCH',
        initial_cash='20000', source_hashes=pins, output_directory=OUTPUT, arm_bindings=bindings,
        prepared_sha256=canonical_hash(prepared), contract_path=CONTRACT, contract_sha256=CONTRACT_SHA,
        sealed_receipt_sha256=SEALED_RECEIPT_SHA, comparison=comparison,
        search_calls=0, account_writes=False, automatic_promotion=False)
    return prepared, assembled, resolver, receipt


def run_candidate(*, scenario, assembled, ohlc, resolver, pins, progress, run_receipt_sha256):
    if not isinstance(run_receipt_sha256,str) or not re.fullmatch('[0-9a-f]{64}',run_receipt_sha256):
        raise ValueError('RUN_RECEIPT_HASH_REQUIRED')
    if pins.get(CONTRACT) != CONTRACT_SHA:
        raise ValueError('DECLARED_MA9_CONTRACT_PIN_REQUIRED')
    configured = prepare_arm(assembled, scenario, pins)
    binding = dict(schema='COST_STRESS_ARM_BINDING_V1', arm=ARM, scenario=scenario,
        initial_cash='20000', continuous_iterations=32, max_objective_evaluations=8192,
        source_hashes=pins, **SCENARIOS[scenario])
    # Match existing cost binding encoding; scenario and arm are explicit.
    digest = hashlib.sha256(json.dumps(binding,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    result = run_cost_ma9_sma20_half_next_open(assembled=configured,ohlc=ohlc,
        history_resolver=resolver,initial_cash='20000',progress=progress,**SCENARIOS[scenario])
    result.update(cost_stress_arm=ARM,cost_stress_scenario=scenario,cost_stress_binding=binding,
        cost_stress_binding_sha256=digest,automatic_promotion=False,costs_are_research_assumptions=True)
    result['research_run_binding'] = dict(receipt_sha256=run_receipt_sha256,
        contract_path=CONTRACT,contract_sha256=CONTRACT_SHA,candidate=ARM)
    result['cost_stress_monthly_bindings'] = [dict(arm_binding_sha256=digest,
        decision_date=row['decision_date'],account_state=deepcopy(row['account_state']))
        for row in result['selection_account_states']]
    return result


@integer_text_limit()
def run_once(output_directory=OUTPUT, expected_receipt_sha256=None, execute=False):
    output = (ROOT/output_directory).resolve()
    if output != (ROOT/OUTPUT).resolve(): raise ValueError('FIXED_ONCE_ONLY_OUTPUT_REQUIRED')
    if execute and output.exists(): raise FileExistsError('EXISTING_RUN_NO_RETRY')
    prepared,assembled,resolver,receipt = prepare_run()
    digest = canonical_hash(receipt)
    if not execute: return dict(status='PREFLIGHT_ONLY_NO_SEARCH',receipt=receipt,receipt_sha256=digest)
    if expected_receipt_sha256 != digest: raise ValueError('REVIEWED_RECEIPT_SHA256_REQUIRED')
    verify_pins(receipt['source_hashes'])
    output.mkdir(parents=True,exist_ok=False)
    def save(path,value):
        with path.open('x',encoding='utf8') as handle:
            json.dump(value,handle,ensure_ascii=False,indent=2);handle.flush();os.fsync(handle.fileno())
    stamp = lambda:datetime.now(timezone.utc).isoformat()
    try:
        save(output/'started.json',dict(at=stamp(),pid=os.getpid(),receipt_sha256=digest))
        save(output/'preflight.json',receipt)
        reports={}
        with patch('urllib.request.urlopen',side_effect=AssertionError('OFFLINE_MA9_SMA20')):
            for scenario in SCENARIOS:
                verify_pins(receipt['source_hashes'])
                directory=output/(scenario+'__'+ARM);directory.mkdir(exist_ok=False)
                save(directory/'started.json',dict(at=stamp(),scenario=scenario,arm=ARM))
                def progress(row):
                    with (directory/'progress.jsonl').open('a',encoding='utf8') as handle:
                        handle.write(json.dumps(row)+'\n');handle.flush();os.fsync(handle.fileno())
                result=run_candidate(scenario=scenario,assembled=deepcopy(assembled),ohlc=deepcopy(prepared['ohlc']),
                    resolver=resolver,pins=receipt['source_hashes'],progress=progress,run_receipt_sha256=digest)
                save(directory/'outcome.json',result)
                verify_pins(receipt['source_hashes'])
                save(directory/'terminal.json',dict(status=result['status'],at=stamp(),
                    outcome_sha256=hashlib.sha256((directory/'outcome.json').read_bytes()).hexdigest()))
                if result['status']!='COMPLETE':raise ValueError('CANDIDATE_NOT_COMPLETE:'+scenario)
                reports[scenario]=summarize(result,assembled,prepared['ohlc'])
                save(directory/'metrics.json',reports[scenario])
        comparisons={}
        for scenario,current in reports.items():
            comparisons[scenario]={}
            for old_arm in ('continuous32_half','continuous32'):
                old=receipt['comparison']['arms'][scenario][old_arm]
                comparisons[scenario][old_arm]=dict(joint_improvement=
                    Fraction(current['final_equity'])>=Fraction(old['final_equity']) and
                    Fraction(current['maximum_close_drawdown'])<Fraction(old['maximum_close_drawdown']),
                    final_equity_difference=str(Fraction(current['final_equity'])-Fraction(old['final_equity'])),
                    drawdown_difference=str(Fraction(current['maximum_close_drawdown'])-Fraction(old['maximum_close_drawdown'])))
        verify_pins(receipt['source_hashes'])
        save(output/'comparison.json',dict(status='PENDING_INDEPENDENT_REVIEW',candidate=ARM,arms=reports,
            comparisons=comparisons,primary_comparator='continuous32_half',both_scenarios_joint_improvement=all(
                item['continuous32_half']['joint_improvement'] for item in comparisons.values()),automatic_promotion=False))
        result=dict(status='COMPLETE_PENDING_INDEPENDENT_REVIEW',at=stamp(),source_pins_unchanged=True,automatic_promotion=False)
        save(output/'terminal.json',result);return result
    except BaseException as error:
        save(output/'terminal.json',dict(status='FAILED',at=stamp(),error_type=type(error).__name__,
            reason=str(error),automatic_retry_allowed=False));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    parser.add_argument('--expected-receipt-sha256');args=parser.parse_args()
    print(json.dumps(run_once(execute=args.execute,expected_receipt_sha256=args.expected_receipt_sha256),indent=2))
