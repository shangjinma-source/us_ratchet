"""Extract current conditional strategy rules without executing strategy code.

The result is a source-bound draft input for a new protocol, never registration.
AST extracts establish reviewed syntax/configuration, not full runtime equivalence.
"""
import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path

from scripts.preflight_quantity_v2_forward_registration import safe, merge_pins

SELECTOR = 'data/current_research_capital_decision_v2.py'
TRAINING = 'backtest/return_priority_monthly_training_inputs.py'
SELL = 'data/current_quantity_v2_difference_plan.py'
CADENCE = 'scripts/run_scheduled_quantity_v2_simulation.py'
CAPITAL = 'data/current_quantity_v2_monthly_training.py'


def build(*, root, request):
    root = Path(root).resolve()
    verified = {}

    def raw(name, digest):
        merge_pins(verified, {name:digest})
        value = safe(root, name).read_bytes()
        if sha256(value).hexdigest() != digest:
            raise ValueError('SEMANTIC_SOURCE_CHANGED')
        verified[name] = digest
        return value

    def document(ref):
        return json.loads(raw(ref['path'], ref['sha256']))

    bootstrap, daily, declared = [document(request[k]) for k in ('bootstrap','daily','dependencies')]
    descriptor = document(bootstrap['descriptor'])
    pins = merge_pins(declared['source_hashes'], descriptor['source_hashes'])
    for reference in request.get('additional_pin_manifests', []):
        field = reference['field']
        if field not in ('source_hashes', 'source_pins'):
            raise ValueError('UNSUPPORTED_PIN_MANIFEST_FIELD')
        extra = document(reference)
        pins = merge_pins(pins, extra[field])
    for name, digest in pins.items():
        raw(name, digest)
    source = document(dict(path=descriptor['input_path'], sha256=pins[descriptor['input_path']]))
    args = source['search_arguments']
    fees = document(bootstrap['fees'])
    fields = {}

    def extracted(key, value, evidence, status='EXTRACTED_CONFIGURATION'):
        fields[key] = dict(status=status, value=value, evidence=evidence)

    def unresolved(key, detail):
        fields[key] = dict(status='UNRESOLVED', reason=detail)

    def syntax(key, path, choose, interpret=lambda nodes: [ast.unparse(n) for n in nodes], single=False):
        if path not in pins:
            unresolved(key, 'Executable source not in supplied approved pins: '+path)
            return
        tree = ast.parse(raw(path, pins[path]))
        nodes = choose(tree)
        if not nodes:
            unresolved(key, 'Expected executable syntax not found: '+path)
            return
        if single and len(nodes) != 1:
            unresolved(key, 'Ambiguous executable candidates: '+path)
            fields[key]['candidates'] = [dict(line=n.lineno, expression=ast.unparse(n)) for n in nodes]
            return
        try:
            value = interpret(nodes)
        except (ValueError, TypeError, IndexError):
            unresolved(key, 'Executable syntax is not statically literal: '+path)
            return
        extracted(key, value, dict(path=path, sha256=pins[path],
            syntax=[dict(line=n.lineno, expression=ast.unparse(n)) for n in nodes]), 'EXTRACTED_EXECUTABLE_SYNTAX')

    def assignments(tree, variable):
        return [n for n in ast.walk(tree) if isinstance(n,ast.Assign)
                and any(isinstance(t,ast.Name) and t.id==variable for t in n.targets)]

    def training_values(nodes):
        values = dict(calendar_length_constraints=[], range_arguments=[], scenario_date_slices=[])
        for node in nodes:
            if isinstance(node,ast.Compare):
                values['calendar_length_constraints'].append(dict(operator=type(node.ops[0]).__name__,
                    value=ast.literal_eval(node.comparators[0])))
            elif isinstance(node,ast.Call):
                values['range_arguments'].append([ast.literal_eval(arg) for arg in node.args])
            else:
                values['scenario_date_slices'].append(dict(start=ast.literal_eval(node.slice.lower) if node.slice.lower else None,
                    stop=ast.literal_eval(node.slice.upper) if node.slice.upper else None,
                    step=ast.literal_eval(node.slice.step) if node.slice.step else None))
        return values

    syntax('selection_method', SELECTOR, lambda t:assignments(t,'VERSION'),
           lambda n:ast.literal_eval(n[0].value), single=True)
    extracted('selection_configuration', {k:args[k] for k in
        ('max_objective_evaluations','fixed_seed','fee_bps','minimum_cash_buffer','decision_date','price_basis')},
        dict(path=descriptor['input_path'], sha256=pins[descriptor['input_path']], json_pointer='/search_arguments'))
    extracted('saved_training_dimensions',dict(scenario_count=len(args['training_scenarios']),
        scenario_dates=args['scenario_dates'],security_count=len(args['prices'])),
        dict(path=descriptor['input_path'],sha256=pins[descriptor['input_path']] ))
    syntax('training_window_and_partition',TRAINING,
        lambda t:[n for n in ast.walk(t) if
            (isinstance(n,ast.Compare) and isinstance(n.left,ast.Call) and ast.unparse(n.left)=='len(days)')
            or (isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='range')
            or (isinstance(n,ast.Subscript) and ast.unparse(n.value)=='days' and isinstance(n.slice,ast.Slice))],training_values)
    extracted('initial_account',dict(initial_cash=bootstrap['initial_cash'],simulation_id=bootstrap['simulation_id'],
        account_id=bootstrap.get('account_id'),scope=bootstrap.get('scope')),
        request['bootstrap'])
    extracted('fee_model',fees,bootstrap['fees'])
    extracted('buy_policy',bootstrap['pullback']['policy'],request['bootstrap'])
    extracted('fill_model',bootstrap['model'],request['bootstrap'])
    syntax('sell_price_expression',SELL,lambda t:assignments(t,'sell'))
    syntax('sell_trigger',SELL,lambda t:[n for n in ast.walk(t) if isinstance(n,ast.If)
        and ast.unparse(n.test)=='delta < 0'])
    syntax('daily_clock_gate',CADENCE,lambda t:[n for n in ast.walk(t) if isinstance(n,ast.If)
        and isinstance(n.test,ast.Compare) and ast.unparse(n.test.left)=='(ny.hour, ny.minute)'],
        lambda nodes:dict(required_local_hour_minute=ast.literal_eval(nodes[0].test.comparators[0]),
                         comparison_operator=type(nodes[0].test.ops[0]).__name__,
                         outside_window_body=[ast.unparse(n) for n in nodes[0].body]),single=True)
    syntax('daily_clock_zone',CADENCE,lambda t:[n for n in ast.walk(t) if isinstance(n,ast.Call)
        and isinstance(n.func,ast.Name) and n.func.id=='ZoneInfo'],
        lambda nodes:[ast.literal_eval(n.args[0]) for n in nodes])
    syntax('monthly_account_capital',CAPITAL,lambda t:[n for n in ast.walk(t) if isinstance(n,ast.Assign)
        and any(isinstance(target,ast.Subscript) and ast.unparse(target)=="data['search_arguments']['entered_cash']" for target in n.targets)])
    aligned, differences = {}, []
    for key in ('root','database_path','account_id','simulation_id','pullback'):
        if key not in bootstrap or key not in daily:
            differences.append(dict(field=key, reason='MISSING',
                missing_in=[name for name,doc in (('bootstrap',bootstrap),('daily',daily)) if key not in doc]))
        elif bootstrap[key] != daily[key]:
            differences.append(dict(field=key,reason='DIFFERENT'))
        else:
            aligned[key]=bootstrap[key]
    for key, prefix in (('fees','fees'),('schedule','schedule')):
        if key not in bootstrap or prefix+'_path' not in daily or prefix+'_sha256' not in daily:
            differences.append(dict(field=key,reason='MISSING'))
        elif bootstrap[key] != dict(path=daily[prefix+'_path'],sha256=daily[prefix+'_sha256']):
            differences.append(dict(field=key,reason='DIFFERENT'))
        else:
            aligned[key]=bootstrap[key]
    if differences:
        unresolved('bootstrap_daily_alignment','Missing or different runtime fields; no whole-account alignment claim.')
        fields['bootstrap_daily_alignment'].update(differences=differences,matched_fields=aligned)
    else:
        extracted('bootstrap_daily_alignment',aligned,request['daily'])
    if 'monthly_plan' in request:
        plan = document(request['monthly_plan'])
        domain_pins = plan['domain_source_hashes']
        for name,digest in domain_pins.items():
            raw(name,digest)
        domain = document(dict(path=plan['domain_path'],sha256=domain_pins[plan['domain_path']]))
        symbols = {row['ticker'] for row in args['metadata'].values()}
        members = set(domain['members'])
        if (set(args['prices']) != set(args['metadata']) or len(symbols)!=len(args['metadata'])
                or len(members)!=len(domain['members']) or members != symbols
                or len(members) != domain['fixed_security_count']):
            unresolved('domain','Monthly declared member set differs from actual saved selector metadata.')
        else:
            extracted('domain',{k:domain[k] for k in ('schema','members','fixed_security_count',
                'point_in_time_membership_verified','new_membership_observation','exclusions')},
                dict(path=plan['domain_path'],sha256=domain_pins[plan['domain_path']],
                    selector_input=descriptor['input_path'],matching_member_sets=True))
    else:
        unresolved('domain','Explicit hash-bound monthly domain plan required; count alone does not prove fixed98.')
    for key, reason in {
        'buy_formula_runtime_equivalence':'Policy values extracted; full pullback/cap path equivalence requires separate review.',
        'monthly_runtime_binding':'A planned domain and capital expression do not prove future paper monthly publication/bind.',
        'source_timing_and_actions':'No PIT source availability or comprehensive action completeness is certified.',
        'forward_registration':'No new protocol or activation receipt is created.',
        'dependency_runtime_equivalence':'Source bytes and AST syntax do not prove exhaustive dynamic execution closure.',
    }.items():
        unresolved(key,reason)
    for name,digest in verified.items():
        if sha256(safe(root,name).read_bytes()).hexdigest()!=digest:
            raise ValueError('SEMANTIC_SOURCE_CHANGED_DURING_READ')
    return dict(schema='QUANTITY_V2_SOURCE_BOUND_SEMANTIC_MANIFEST_V1',status='DRAFT_SEMANTICS_WITH_UNRESOLVED',
        rules=fields,source_hashes=verified,registered=False,account_writes=False,filesystem_writes=False,
        economic_search_calls=0,protocol_equivalence_certified=False,
        purpose='Normalized evidence input for a separately reviewed replacement protocol; not READY or activation.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True);parser.add_argument('--request',required=True)
    args=parser.parse_args();root=Path(args.root).resolve()
    result=build(root=root,request=json.loads(safe(root,args.request).read_bytes()))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
