"""Guard against comparing empty startup, hiding failures, or changing cohorts."""
import json
import unittest
from pathlib import Path

from payload_load import select_loaded_window, validate_observations
from build_site import attach_payloads, GENESIS, PAYLOAD_KIND


def row(slot, node=1, tx=100, size=65000):
    return [0, node, slot, tx, size, tx*21000, 2, 400, f'root{slot}', 0, 0]


class PayloadLoadTests(unittest.TestCase):
    def test_payload_profile_deduplicates_imports_and_preserves_both_clocks(self):
        first = row(20)
        first[9] = GENESIS[0]+20*12000+730
        replay = first.copy()
        replay[7] = 1600
        replay[9] += 2000
        detail = {'slots': [20,21], 'events': []}
        attach_payloads(detail, [replay, first, first, row(99)], 0, 1)
        self.assertEqual(len(detail['payloads']), 1)
        self.assertEqual(detail['payloads'][0][-2:], [400,730])
        self.assertEqual(detail['events'], [
            [0,20,4,PAYLOAD_KIND,0,0,1,1,65000,0],
            [1,20,7,PAYLOAD_KIND,0,0,1,1,65000,0]])
        self.assertNotIn('network', detail)

    def test_absent_payload_instrumentation_is_marked_unavailable(self):
        detail = {'slots': [20], 'events': []}
        attach_payloads(detail, [row(20)], 0, 50)
        self.assertFalse(detail['payload_instrumented'])
        self.assertEqual(detail['events'], [])

    def test_empty_and_small_payload_startup_excluded(self):
        rows = [row(s, tx=0, size=839) if s < 5 else row(s, size=2000) if s < 10 else row(s)
                for s in range(30)]
        result = select_loaded_window(rows, 0, range(30), [1])
        self.assertEqual(result['selected_slots'], list(range(10,30)))
        self.assertEqual(result['confirmed_payload_slots'], 20)

    def test_confirmation_cannot_bridge_capture_gap(self):
        slots = list(range(8))+list(range(20,40))
        result = select_loaded_window([row(s) for s in slots], 0, slots, [1])
        self.assertEqual(result['first_selected_slot'], 20)

    def test_known_missed_slot_stays_in_denominator(self):
        rows = [row(s) for s in range(30) if s != 25]
        result = select_loaded_window(rows, 0, range(30), [1], allowed_missing=[25])
        self.assertEqual(len(result['selected_slots']), 30)
        self.assertEqual(result['confirmed_payload_slots'], 29)
        self.assertEqual(result['slots_without_payload'], [25])

    def test_return_to_empty_payload_is_not_silently_dropped(self):
        rows = [row(s, tx=0, size=839) if s == 25 else row(s) for s in range(30)]
        with self.assertRaisesRegex(ValueError, 'load stopped'):
            select_loaded_window(rows, 0, range(30), [1])

    def test_unexplained_missing_payload_fails(self):
        with self.assertRaisesRegex(ValueError, 'Unexplained missing'):
            select_loaded_window([row(s) for s in range(30) if s != 25], 0, range(30), [1])

    def test_cohort_must_have_confirmation_on_each_node(self):
        rows = [row(s) for s in range(30)]+[row(s, node=2) for s in range(10,30)]
        result = select_loaded_window(rows, 0, range(30), [1,2])
        self.assertEqual(result['first_selected_slot'], 10)

    def test_duplicate_imports_do_not_inflate_payload_statistics(self):
        rows = [row(s) for s in range(30)]
        result = select_loaded_window(rows+rows[:10], 0, range(30), [1])
        self.assertEqual(result['confirmed_payload_slots'], 30)
        self.assertEqual(result['observations_by_node']['1'], 30)

    def test_conflicting_payload_evidence_fails(self):
        rows = [row(s) for s in range(30)]
        with self.assertRaisesRegex(ValueError, 'Conflicting payload'):
            select_loaded_window(rows+[row(20, tx=101)], 0, range(30), [1])

    def test_real_execution_export_crosscheck(self):
        data = json.loads((Path(__file__).resolve().parents[1]/'results/payload-observations.json').read_text())
        result = validate_observations(data)
        self.assertEqual(result['first_genesis_first_transaction_slot'], 308)
        self.assertEqual(result['execution_checked_slots'], 544)
        self.assertEqual(result['execution_tx_and_gas_mismatches'], 0)
        data['execution_rows'][1][2] += 1
        with self.assertRaisesRegex(ValueError, 'Execution export disagrees'):
            validate_observations(data)


if __name__ == '__main__':
    unittest.main()
