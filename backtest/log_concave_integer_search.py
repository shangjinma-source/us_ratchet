"""Exact integer maximization for a positive log-concave objective.

The caller must establish log concavity. In the portfolio caller every scenario
wealth is positive affine in quantity; summing its logarithm is concave. Thus
adjacent objective comparisons locate the leftmost integer maximum. No floating
point logarithms or derivatives are required. This does not optimize supports.
"""


def maximize_log_concave_integer(minimum, maximum, objective):
    if type(minimum) is not int or type(maximum) is not int or minimum > maximum:
        raise ValueError('Ordered integer bounds required')
    low, high = minimum, maximum
    while low < high:
        middle = (low + high) // 2
        if objective(middle) >= objective(middle + 1):
            high = middle
        else:
            low = middle + 1
    return low
