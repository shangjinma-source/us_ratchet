"""Bounded paper market continuation, anchored to a fixed policy and prior receipts.

The seed is shared read-only with its existing producer. Successors use a
separate paper directory. One call prepares at most one unfinished month.
No account, selection, trading, task changes, or replacement of partial files.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import os

from core.strategy_account_ledger import canonical, require
from data.strategy_paper_application_descriptor_v2 import NY, stamp
from scripts.build_real_monthly_release_entry import build as build_entry
from scripts.materialize_paper_monthly_successor_v3 import run as materialize
from scripts.run_real_monthly_market_preparation import bounded, run as produce


def month_number(value):
    require(isinstance(value, str) and len(value) == 7, 'PAPER_CHAIN_MONTH')
    parsed = datetime.strptime(value, '%Y-%m')
    require(parsed.strftime('%Y-%m') == value, 'PAPER_CHAIN_MONTH')
    return parsed.year * 12 + parsed.month - 1


def next_month(value):
    year, month = divmod(month_number(value) + 1, 12)
    return f'{year:04d}-{month + 1:02d}'


def run(*, root, policy_reference, execute=False, target_month=None,
        clock=lambda: datetime.now(timezone.utc), transports=None):
    """target_month resolves existing evidence only, regardless of execute.

    Maintenance (no target_month) can materialize successor plans and invoke
    their producer. The calling registered runtime must pin this code closure.
    """
    root = Path(root).resolve()
    inputs = {}

    def raw(path, digest=None):
        source = bounded(root, path)
        require(source.is_file() and source.stat().st_size <= 32 * 1024 * 1024,
                'PAPER_CHAIN_SOURCE_UNAVAILABLE')
        body = source.read_bytes()
        actual = sha256(body).hexdigest()
        require(digest is None or actual == digest, 'PAPER_CHAIN_SOURCE_CHANGED')
        name = source.relative_to(root).as_posix()
        require(name not in inputs or inputs[name] == actual, 'PAPER_CHAIN_SOURCE_CHANGED')
        inputs[name] = actual
        return body

    def reference(ref):
        require(type(ref) is dict and set(ref) == {'path', 'sha256'}, 'PAPER_CHAIN_REFERENCE')
        return raw(ref['path'], ref['sha256'])

    policy = json.loads(reference(policy_reference))
    require(set(policy) == {'schema', 'authorization', 'first_month', 'terminal_month', 'seed', 'output_root'}
            and policy['schema'] == 'PAPER_MONTHLY_CHAIN_V3'
            and policy['authorization'] == 'SHARED_SEED_READ_ONLY_PAPER_SUCCESSORS', 'PAPER_CHAIN_POLICY')
    first, terminal = policy['first_month'], policy['terminal_month']
    require(0 <= month_number(terminal) - month_number(first) < 24, 'PAPER_CHAIN_STUDY_RANGE')
    if target_month is not None:
        require(month_number(first) <= month_number(target_month) <= month_number(terminal),
                'PAPER_CHAIN_TARGET_OUTSIDE_STUDY')
    output = bounded(root, policy['output_root']).relative_to(root).as_posix()
    slot, month = deepcopy(policy['seed']), first
    failures = []

    def finish(status, **extra):
        for path, digest in inputs.items():
            require(sha256(bounded(root, path).read_bytes()).hexdigest() == digest,
                    'PAPER_CHAIN_CHANGED_DURING_READ')
        require(not any(path.exists() for path in failures), 'PAPER_CHAIN_FAILED_PRESERVED')
        return dict(status=status, target_month=month, slot=slot, account_writes=False, **extra)

    for _ in range(24):
        require(set(slot) == {'complete_path', 'expected_binding', 'producer_inputs', 'runtime_descriptor'},
                'PAPER_CHAIN_SLOT')
        binding, producer = slot['expected_binding'], slot['producer_inputs']
        require(set(binding) == {'coordinator_sha256', 'bootstrap_sha256', 'policy_path', 'policy_sha256', 'output_directory'}
                and set(producer) == {'coordinator', 'bootstrap', 'policy'}, 'PAPER_CHAIN_BINDING')
        require(producer['coordinator']['sha256'] == binding['coordinator_sha256']
                and producer['bootstrap']['sha256'] == binding['bootstrap_sha256']
                and producer['policy'] == dict(path=binding['policy_path'], sha256=binding['policy_sha256'])
                and slot['complete_path'] == binding['output_directory'] + '/complete.json',
                'PAPER_CHAIN_BINDING')
        for ref in producer.values():
            reference(ref)
        reference(slot['runtime_descriptor'])
        coordinator = json.loads(reference(producer['coordinator']))
        require(Path(coordinator['root']).resolve() == root and coordinator['session'][:7] == month,
                'PAPER_CHAIN_COORDINATOR_MONTH')
        completion = bounded(root, slot['complete_path'])
        failure = completion.parent / 'failed.json'
        failures.append(failure)
        require(not failure.exists(), 'PAPER_CHAIN_FAILED_PRESERVED')
        if not completion.is_file():
            require(not completion.parent.exists(), 'PAPER_CHAIN_PARTIAL_OUTPUT_RECOVERY_REQUIRED')
            if month == first:
                settings = json.loads(raw(coordinator['settings_path'], coordinator['settings_sha256']))
                boundary_path = settings['calendar_path']
                boundary = json.loads(raw(boundary_path, settings['fixed_source_hashes'][boundary_path]))
                require(stamp(clock()) < stamp(boundary['active_open_at']),
                        'PAPER_CHAIN_SHARED_SEED_RECOVERY_REQUIRED')
                return finish('WAIT_SHARED_SEED_COMPLETION')
            if target_month is not None:
                return finish('WAIT_MONTHLY_PUBLICATION')
            result = produce(coordinator_config=bounded(root, producer['coordinator']['path']),
                coordinator_sha256=producer['coordinator']['sha256'],
                bootstrap_config=bounded(root, producer['bootstrap']['path']),
                bootstrap_sha256=producer['bootstrap']['sha256'],
                policy_path=producer['policy']['path'], policy_sha256=producer['policy']['sha256'],
                output_directory=binding['output_directory'], execute=execute, clock=clock,
                **dict(transports or {}))
            # A producer result is not sufficient evidence of a usable release.
            if result['status'] == 'MARKET_PUBLICATION_READY_NOT_ACTIVATED':
                verify_complete(root, slot, month, raw, clock)
            return finish(result['status'], producer_result=result)
        digest = verify_complete(root, slot, month, raw, clock)
        if month == target_month:
            return finish('MONTHLY_PUBLICATION_VERIFIED', complete_sha256=digest)
        if month == terminal:
            return finish('PAPER_MONTHLY_CHAIN_COMPLETE')
        successor_month = next_month(month)
        plan_directory = output + '/' + successor_month + '/plan'
        descriptor = slot['runtime_descriptor']
        generated = materialize(root=root, complete_path=slot['complete_path'], complete_sha256=digest,
            descriptor_path=descriptor['path'], descriptor_sha256=descriptor['sha256'],
            output_directory=plan_directory, expected_binding=binding, terminal_month=terminal,
            execute=execute and target_month is None, clock=clock)
        require(generated['target_month'] == successor_month, 'PAPER_CHAIN_SUCCESSOR_MONTH')
        if generated['status'] == 'PAPER_SUCCESSOR_PREFLIGHT':
            return finish('SUCCESSOR_PLAN_REQUIRED' if target_month is not None else 'SUCCESSOR_PLAN_PREFLIGHT',
                          next_month=successor_month)
        materialization = json.loads(raw(plan_directory + '/materialization.complete.json'))
        for path, digest in materialization['output_hashes'].items():
            raw(path, digest)
        month = successor_month
        producer = deepcopy(producer)
        producer['coordinator'] = dict(path=generated['coordinator_path'], sha256=generated['coordinator_sha256'])
        market = output + '/' + month + '/market'
        binding = dict(binding, coordinator_sha256=generated['coordinator_sha256'], output_directory=market)
        slot = dict(complete_path=market + '/complete.json', expected_binding=binding,
                    producer_inputs=producer, runtime_descriptor=descriptor)
    raise ValueError('PAPER_CHAIN_DEPTH_EXCEEDED')


def verify_complete(root, slot, month, read, clock):
    body = read(slot['complete_path'])
    receipt = json.loads(body)
    require(receipt['binding'] == slot['expected_binding'] and stamp(receipt['at']) <= stamp(clock()),
            'PAPER_CHAIN_COMPLETION_BINDING')
    digest = sha256(body).hexdigest()
    descriptor = slot['runtime_descriptor']
    entry = build_entry(root=root, complete_path=slot['complete_path'], complete_sha256=digest,
                        descriptor_path=descriptor['path'], descriptor_sha256=descriptor['sha256'])
    require(entry['target_month'] == month, 'PAPER_CHAIN_PUBLICATION_MONTH')
    for path, source_hash in receipt['output_hashes'].items():
        read(path, source_hash)
    return digest


def load_published_month(*, root, policy_reference, runtime_pins, output_root, clock=None):
    """Select only the current New York month's verified chain publication."""
    from data.strategy_paper_monthly_training_bridge_v2 import load_monthly_training
    root = Path(root).resolve()
    clock = clock or (lambda: datetime.now(timezone.utc))
    month = stamp(clock()).astimezone(NY).strftime('%Y-%m')
    arguments = dict(root=root, policy_reference=policy_reference, target_month=month, clock=clock)
    resolved = run(**arguments)
    require(resolved['status'] == 'MONTHLY_PUBLICATION_VERIFIED',
            'PAPER_CHAIN_TRAINING_' + resolved['status'])
    slot = resolved['slot']
    descriptor = slot['runtime_descriptor']
    entry = build_entry(root=root, complete_path=slot['complete_path'],
        complete_sha256=resolved['complete_sha256'], descriptor_path=descriptor['path'],
        descriptor_sha256=descriptor['sha256'])
    body = canonical(dict(schema='REAL_STRATEGY_MONTHLY_RELEASES_V1', entries=[entry]))
    digest = sha256(body).hexdigest()
    destination = bounded(root, output_root)
    destination.mkdir(parents=True, exist_ok=True)
    registry = bounded(root, destination / (digest + '.json'))
    if not registry.exists():
        try:
            with registry.open('xb') as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            pass
    require(registry.read_bytes() == body, 'PAPER_CHAIN_DERIVED_REGISTRY_CHANGED')
    loaded = load_monthly_training(root=root, registry_path=registry.relative_to(root).as_posix(),
        registry_sha256=digest, runtime_pins=runtime_pins, output_root=destination/'selection', clock=clock)
    require(run(**arguments) == resolved, 'PAPER_CHAIN_CHANGED_DURING_TRAINING_READ')
    loaded['producer_complete_sha256'] = resolved['complete_sha256']
    loaded['publication_policy_reference'] = dict(policy_reference)
    return loaded
