from copy import deepcopy
import unittest
from scripts import ndx_dated_path_risk_display_independent_readback_20261003 as reader
from test_ndx_dated_path_risk_display_independent_readback_20261003 import stream_fixture, inspect


def rewrite(data, rows):
    offset = 0
    lines = []
    entries = [e for e in data[1]['task_index'] if e['jsonl_record'] is not None]
    for number, (entry, row) in enumerate(zip(entries, rows)):
        blob = reader.enc(row) + b'\n'
        entry['jsonl_record'] = dict(record_index=number, byte_start=offset,
            byte_stop=offset + len(blob), row_sha256=reader.sha(blob))
        lines.append(blob)
        offset += len(blob)
    data[0] = b''.join(lines)
    data[1]['task_jsonl_reference'].update(sha256=reader.sha(data[0]), byte_count=offset)


class Tests(unittest.TestCase):
    def test_resigned_authority_or_scope_upgrade_rejected(self):
        for key, value in [('source_bytes_authenticated', True), ('economics_recomputed', True),
                           ('scope', 'OFFICIAL_PIT_PROVEN')]:
            data = list(stream_fixture())
            rows = [reader.loads(line) for line in data[0].splitlines()]
            rows[0][key] = value
            rewrite(data, rows)
            with self.subTest(key=key), self.assertRaises(ValueError):
                inspect(data)

    def test_fixed_source_collision_not_last_value_wins(self):
        base = {'fixed': 'a' * 64}
        refs = [dict(path='fixed', sha256='b' * 64)]
        with self.assertRaises(ValueError):
            reader.check_source_closure({'fixed': 'b' * 64}, base, refs)
        with self.assertRaises(ValueError):
            reader.check_source_closure(base, base, [dict(path='extra', sha256='a' * 64)])

    def test_equal_nav_values_do_not_permit_mode_link_swap(self):
        data = list(stream_fixture())
        rows = [reader.loads(line) for line in data[0].splitlines()]
        first, second = reader.MODES
        links = rows[0]['nav_modes']
        links[first], links[second] = links[second], links[first]
        rewrite(data, rows)
        with self.assertRaises(ValueError):
            inspect(data)


if __name__ == '__main__':
    unittest.main()
