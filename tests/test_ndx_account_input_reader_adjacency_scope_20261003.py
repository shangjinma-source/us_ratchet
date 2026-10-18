"""Independent rejection of skipped strategy-prior periods."""
from copy import deepcopy
from unittest import TestCase, main
from scripts import ndx_multidecision_account_inputs_independent_readback_20261003 as reader
from test_ndx_multidecision_account_inputs_independent_readback_20261003 import inputs, resign


class AdjacencyTests(TestCase):
    def test_equal_weights_do_not_allow_skipping_missing_previous_period(self):
        arguments = inputs()
        # All successful targets happen to be equal; equality alone cannot
        # establish that the previous monthly observation actually exists.
        missing = arguments['outer_rows'][12]
        missing.update(evidence=None, status='NO_REFIT_INPUT_OR_ADJACENT_PRIOR')
        arguments['saved']['outer_coordinate_rows_preserved'] = deepcopy(arguments['outer_rows'])
        resign(arguments)
        with self.assertRaisesRegex(ValueError, '[Aa]djacent'):
            reader.inspect_projection(**arguments)


if __name__ == '__main__':
    main()
