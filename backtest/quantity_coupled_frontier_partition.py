"""Independent structural coverage audit before resuming a coupled search.

Checks traversal and suffix partition only. It does not authenticate numerical
pruning proofs, input data, feasibility, or optimality; the source verifier
must establish those separately. No objective evaluation or IO.
"""
from math import prod

from backtest.quantity_integer_box_certificate_prototype import require


def verify(certificate):
    require(certificate['schema'] == 'COUPLED_JOINT_LOSS_ITERATOR_V1', 'SCHEMA_CHANGED')
    axes = certificate['axes']
    require(len({axis['sid'] for axis in axes}) == len(axes), 'DUPLICATE_AXIS')
    require(all(type(axis['max_deviation']) is int and axis['max_deviation'] > 0
                for axis in axes), 'INVALID_AXIS_WIDTH')
    widths = [axis['max_deviation'] + 1 for axis in axes]
    stack = [[]]
    closed_patterns = 0
    point_indices = []
    for record in certificate['ledger']:
        require(bool(stack), 'TRAVERSAL_AFTER_COMPLETION')
        prefix = stack.pop()
        actual = record['prefix']
        require(type(actual) is list and all(type(d) is int for d in actual)
                and actual == prefix, 'PREFIX_ORDER_OR_COVERAGE_CHANGED')
        terminal = record['terminal']
        if terminal == 'SPLIT_ALL_ALLOWED_DEVIATIONS':
            require(len(prefix) < len(axes), 'SPLIT_PAST_LEAF')
            axis = axes[len(prefix)]
            require(record['sid'] == axis['sid'] and type(record['maximum']) is int
                    and record['maximum'] == axis['max_deviation'], 'SPLIT_AXIS_CHANGED')
            stack.extend(prefix + [d] for d in range(axis['max_deviation'], -1, -1))
        else:
            require(terminal in {'CLOSED_BY_PREFIX_BUDGET_AND_COORDINATE_LOSS',
                    'CLOSED_BY_COUPLED_BUDGET_LOSS', 'CHECKED_INTEGER_POINT'},
                    'UNKNOWN_TERMINAL')
            if terminal != 'CLOSED_BY_PREFIX_BUDGET_AND_COORDINATE_LOSS':
                require(len(prefix) == len(axes), 'TERMINAL_REQUIRES_LEAF')
            if terminal == 'CHECKED_INTEGER_POINT':
                index = record['point_index']
                require(type(index) is int and index == len(point_indices), 'POINT_ORDER_CHANGED')
                point_indices.append(index)
            closed_patterns += prod(widths[len(prefix):])
    frontier = certificate['unsearched_frontier']
    require(type(frontier) is list and all(type(p) is list and all(type(d) is int for d in p)
            for p in frontier) and frontier == stack, 'FRONTIER_CHANGED')
    pending_patterns = sum(prod(widths[len(prefix):]) for prefix in stack)
    require(closed_patterns + pending_patterns == prod(widths), 'PARTITION_MASS_CHANGED')
    require(type(certificate['domain_complete']) is bool
            and certificate['domain_complete'] == (not stack), 'COMPLETION_CHANGED')
    require(type(certificate['visited_nodes']) is int
            and certificate['visited_nodes'] == len(certificate['ledger']), 'NODE_COUNT_CHANGED')
    require(len(certificate['points']) == len(point_indices)
            and type(certificate['checked_points']) is int
            and certificate['checked_points'] == len(point_indices), 'POINT_COUNT_CHANGED')
    return dict(status='VERIFIED_STRUCTURAL_SUFFIX_PARTITION',
                closed_patterns=closed_patterns, pending_patterns=pending_patterns,
                total_patterns=prod(widths), numerical_proofs_verified=False,
                objective_evaluations=0)
