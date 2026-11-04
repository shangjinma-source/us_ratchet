"""Explicit bounded serialization policy for standalone offline research only."""
import sys

INTEGER_STRING_DIGITS = 100000


def configure_offline_fraction_serialization():
    """Call at the offline process entry, never at import or in production."""
    previous = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(INTEGER_STRING_DIGITS)
    return dict(integer_string_digits=INTEGER_STRING_DIGITS, previous_integer_string_digits=previous,
                scope='STANDALONE_OFFLINE_RESEARCH_PROCESS_ONLY', exact_fraction_arithmetic=True)
