"""Read-only forward registration gap inspection; never registers or executes a strategy."""
import argparse
import ast
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

ENTRYPOINTS = (
    'scripts/bootstrap_current_quantity_v2_simulation.py',
    'scripts/run_scheduled_quantity_v2_simulation.py',
    'scripts/run_current_quantity_v2_simulation.py',
    'scripts/monthly_runtime_routes.py',
)


def merge_pins(*maps):
    result = {}
    for mapping in maps:
        for name, digest in mapping.items():
            if name in result and result[name] != digest:
                raise ValueError('REFERENCE_PIN_CONFLICT')
            result[name] = digest
    return result


def safe(root, name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError('UNSAFE_PATH')
    path = root / name
    if Path(name).is_absolute() or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('UNSAFE_PATH')
    cursor = path
    while cursor != root:
        if cursor.is_symlink() or (hasattr(cursor, 'is_junction') and cursor.is_junction()):
            raise ValueError('PATH_ALIAS')
        cursor = cursor.parent
    if not path.resolve().is_relative_to(root):
        raise ValueError('PATH_ESCAPE')
    return path


def dependency_closure(root, entrypoints, pins):
    """Conservative static walk. Dynamic/external imports remain unresolved gates."""
    pending = list(entrypoints)
    found, issues = {}, []

    def modules(parts):
        if not parts:
            return []
        prefix = '/'.join(parts)
        options = [prefix + '.py', prefix + '/__init__.py']
        return [p for p in options if safe(root, p).is_file()]

    while pending:
        name = pending.pop()
        if name in found:
            continue
        path = safe(root, name)
        if not path.is_file():
            issues.append(dict(code='MISSING_ENTRY_OR_MODULE', path=name))
            continue
        raw = path.read_bytes()
        found[name] = sha256(raw).hexdigest()
        if pins.get(name) != found[name]:
            issues.append(dict(code='DEPENDENCY_UNPINNED_OR_CHANGED', path=name))
        parts = name[:-3].split('/')
        package = parts[:-1]
        for length in range(1, len(package) + 1):
            init = '/'.join(package[:length]) + '/__init__.py'
            if safe(root, init).is_file():
                pending.append(init)
        try:
            tree = ast.parse(raw, filename=name)
        except (SyntaxError, UnicodeError):
            issues.append(dict(code='SOURCE_PARSE_FAILED', path=name))
            continue
        for node in ast.walk(tree):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name.split('.') for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module.split('.') if node.module else []
                if node.level:
                    if node.level > len(package):
                        issues.append(dict(code='RELATIVE_IMPORT_ESCAPE', path=name, line=node.lineno))
                        continue
                    base = package[:len(package) - node.level + 1] + base
                imports = [base]
                for alias in node.names:
                    pending.extend(modules(base + [alias.name]))
            elif isinstance(node, ast.Call):
                call = ast.unparse(node.func)
                if call in ('__import__', 'eval', 'exec') or call.endswith(('.import_module', '.exec_module', '.spec_from_file_location')):
                    issues.append(dict(code='DYNAMIC_CODE_REQUIRES_REVIEW', path=name, line=node.lineno))
            for imported in imports:
                # Even a failed dotted import executes existing local parent
                # packages. Do not hide a local stdlib-name shadow behind the
                # stdlib exemption (e.g. json/__init__.py without decoder.py).
                local_prefix = False
                for length in range(1, len(imported) + 1):
                    prefix = '/'.join(imported[:length])
                    if safe(root, prefix).is_dir():
                        local_prefix = True
                        init = prefix + '/__init__.py'
                        if safe(root, init).is_file():
                            pending.append(init)
                    pending.extend(modules(imported[:length]))
                local = modules(imported)
                if local:
                    pending.extend(local)
                elif imported and safe(root, '/'.join(imported)).is_dir():
                    pass  # Namespace package; imported child modules queued above.
                elif local_prefix:
                    issues.append(dict(code='UNRESOLVED_LOCAL_IMPORT', path=name,
                                       module='.'.join(imported), line=node.lineno))
                elif imported and imported[0] not in sys.stdlib_module_names:
                    issues.append(dict(code='EXTERNAL_OR_UNRESOLVED_IMPORT', path=name,
                                       module='.'.join(imported), line=node.lineno))
    return dict(source_hashes=found, issues=issues, complete=not issues,
                runtime_dependency_closure_certified=False,
                scope='Static AST walk only. Aliased/reflected dynamic imports cannot be exhaustively proven; no complete runtime closure certification.')


def preflight(*, root, request):
    root = Path(root).resolve()
    observed = datetime.now(ZoneInfo('UTC'))  # No caller-controlled production clock.
    checked = {}

    def read(ref):
        name, expected = ref['path'], ref['sha256']
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('INVALID_HASH')
        raw = safe(root, name).read_bytes()
        if sha256(raw).hexdigest() != expected:
            raise ValueError('INPUT_CHANGED')
        if name in checked and checked[name] != expected:
            raise ValueError('REFERENCE_PIN_CONFLICT')
        checked[name] = expected
        return json.loads(raw)

    if request['schema'] != 'QUANTITY_V2_FORWARD_PREFLIGHT_REQUEST_V1':
        raise ValueError('REQUEST_SCHEMA')
    protocol, bootstrap, daily, dependencies = [read(request[key]) for key in
        ('protocol', 'bootstrap', 'daily', 'dependencies')]
    pins = dependencies['source_hashes']
    for name, digest in pins.items():
        if sha256(safe(root, name).read_bytes()).hexdigest() != digest:
            raise ValueError('DEPENDENCY_PIN_CHANGED')
    closure = dependency_closure(root, ENTRYPOINTS, pins)
    descriptor = read(bootstrap['descriptor'])
    for name, digest in descriptor['source_hashes'].items():
        if sha256(safe(root, name).read_bytes()).hexdigest() != digest:
            raise ValueError('DESCRIPTOR_SOURCE_CHANGED')
        if name in pins and pins[name] != digest:
            raise ValueError('PIN_CONFLICT')
    fees = read(bootstrap['fees'])
    schedule = read(bootstrap['schedule'])
    differences = []

    def gap(code, detail):
        differences.append(dict(code=code, detail=detail))

    if 'initial_month' in bootstrap:
        initial = read(bootstrap['initial_month'])
        for name, digest in merge_pins(initial.get('original_source_hashes', {}), initial.get('source_hashes', {})).items():
            if name in checked and checked[name] != digest:
                raise ValueError('REFERENCE_PIN_CONFLICT')
            if sha256(safe(root, name).read_bytes()).hexdigest() != digest:
                raise ValueError('INITIAL_MONTH_SOURCE_CHANGED')
            checked[name] = digest
    else:
        gap('INITIAL_MONTH_REFERENCE_MISSING', 'bootstrap.initial_month')
    identity = bootstrap.get('identity_manifest_path')
    identity_hash = descriptor['source_hashes'].get(identity)
    if identity and identity_hash:
        read(dict(path=identity, sha256=identity_hash))
    else:
        gap('IDENTITY_MANIFEST_HASH_UNBOUND', identity)
    calendar_pins = schedule.get('source_hashes', {})
    if not calendar_pins:
        gap('CALENDAR_PROVENANCE_PINS_MISSING', bootstrap['schedule']['path'])
    for name, digest in calendar_pins.items():
        if name in checked and checked[name] != digest:
            raise ValueError('REFERENCE_PIN_CONFLICT')
        if sha256(safe(root, name).read_bytes()).hexdigest() != digest:
            raise ValueError('CALENDAR_SOURCE_CHANGED')
        checked[name] = digest

    if protocol.get('frozen') is not True or not protocol.get('activation', {}).get('registered_at'):
        gap('PROTOCOL_NOT_REGISTERED', 'Current draft is not an activated forward series.')
    for label, config in (('bootstrap', bootstrap), ('daily', daily)):
        if config.get('protocol_sha256') != request['protocol']['sha256']:
            gap('RUNTIME_PROTOCOL_BINDING_MISSING', label)
    for key in ('root', 'database_path', 'simulation_id', 'pullback'):
        if bootstrap.get(key) != daily.get(key):
            gap('BOOTSTRAP_DAILY_DIFFERENCE', key)
    if bootstrap['fees'] != dict(path=daily['fees_path'], sha256=daily['fees_sha256']):
        gap('FEE_CONFIGURATION_DIFFERENCE', 'Bootstrap and daily fee references differ.')
    if bootstrap['schedule'] != dict(path=daily['schedule_path'], sha256=daily['schedule_sha256']):
        gap('CALENDAR_CONFIGURATION_DIFFERENCE', 'Bootstrap and daily calendar references differ.')
    policy = bootstrap['pullback']['policy']
    execution = protocol.get('execution', {})
    for key in ('rebound_fraction', 'minimum_discount', 'maximum_age_seconds'):
        if execution.get(key) != policy.get(key):
            gap('EXECUTION_POLICY_DIFFERENCE', key)
    # Existing draft fields are evidence, not a new invented activation schema.
    # This inspector cannot certify a future replacement registration format.
    validator = protocol.get('validator_boundary', {})
    if validator.get('status') == 'LEGACY_VALIDATOR_DOES_NOT_VALIDATE_THIS_NEW_SCHEMA':
        gap('LEGACY_VALIDATOR_SCOPE_MISMATCH', dict(path=validator.get('path'), status=validator['status']))
    membership = protocol.get('domain_data_calendar', {}).get('membership')
    if membership:
        gap('DOMAIN_SEMANTICS_NOT_MACHINE_VERIFIED', dict(protocol_membership=membership,
            runtime_descriptor=request['bootstrap']['path'], input_path=descriptor.get('input_path'),
            detail='Listed source hashes do not establish that the actual runtime domain satisfies this declaration.'))
    else:
        gap('PROTOCOL_DOMAIN_DECLARATION_MISSING', 'domain_data_calendar.membership')
    if daily.get('monthly') is None:
        gap('MONTHLY_RUNTIME_NOT_BOUND', 'Base daily configuration has no monthly successor yet.')
    start = request['proposed_start_session']
    rows = [row for row in schedule['sessions'] if row['date'] == start]
    eligible = False
    if len(rows) == 1:
        trigger = datetime.fromisoformat(start + 'T10:00:00').replace(tzinfo=ZoneInfo('America/New_York'))
        opening = datetime.fromisoformat(rows[0]['open_at'])
        closing = datetime.fromisoformat(rows[0]['close_at'])
        eligible = (opening.utcoffset() is not None and closing.utcoffset() is not None
            and opening.astimezone(ZoneInfo('America/New_York')).date().isoformat() == start
            and closing.astimezone(ZoneInfo('America/New_York')).date().isoformat() == start
            and opening < closing and observed < trigger and opening <= trigger < closing)
    if not eligible:
        gap('START_NOT_FUTURE_REGISTERED_SESSION', start)
    if not closure['complete']:
        gap('DEPENDENCY_CLOSURE_INCOMPLETE', 'See individual unresolved/unpinned imports.')
    for name, digest in merge_pins(checked, closure['source_hashes'], pins, descriptor['source_hashes']).items():
        if sha256(safe(root, name).read_bytes()).hexdigest() != digest:
            raise ValueError('SOURCE_CHANGED_DURING_PREFLIGHT')
    return dict(status='NOT_READY',
        scope='CURRENT_DRAFT_REGISTRATION_GAP_INSPECTOR_NOT_GENERAL_ACTIVATION_VALIDATOR',
        readiness_certification_implemented=False,
        unimplemented_checks=['Executable selector/SELL/fill/capital/flow semantic equivalence',
            'Runtime domain membership equivalence to protocol declaration',
            'Forward monthly publication authorization and prospective version transitions',
            'Complete runtime dependency closure including dynamic loading'],
        observed_at=observed.isoformat(), verified_input_hashes=checked,
        dependency_closure=closure, protocol_runtime_differences=differences,
        proposed_start_eligible=eligible, current_trial_scope=bootstrap.get('scope'),
        initial_cash=bootstrap.get('initial_cash'), fill_model=bootstrap.get('model'), fees=fees,
        registered=False, forward_year_started=False, account_writes=False, filesystem_writes=False,
        http_calls=0, existing_authorized_trial_may_continue=True,
        boundary='Diagnostic only; prior trial observations cannot be backfilled into a later forward registration.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--request', required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        result = preflight(root=root, request=json.loads(safe(root, args.request).read_bytes()))
    except Exception as error:
        value = str(error)
        result = dict(status='BLOCKED', reason=value if type(error) is ValueError and re.fullmatch('[A-Z_]+', value) else type(error).__name__, registered=False, account_writes=False)
    print(json.dumps(result, ensure_ascii=False))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
