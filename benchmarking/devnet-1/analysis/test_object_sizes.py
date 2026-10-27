import unittest
from object_sizes import column_bytes, block_floor, apply_sizes, BLOCK_FLOOR


class ObjectSizeTests(unittest.TestCase):
    def test_column_weight_uses_logged_cells_and_proofs(self):
        self.assertEqual(column_bytes(0),56)
        self.assertEqual(column_bytes(3),56+3*(2048+48))
        with self.assertRaises(ValueError):column_bytes(-1)

    def test_block_lower_bound_accounts_for_logged_lists(self):
        self.assertEqual(BLOCK_FLOOR,924)
        self.assertEqual(block_floor({'attestations':'2','blobKzgCommitmentCount':'3'}),924+2*241+3*48)

    def test_sizing_cannot_silently_change_column_event_counts(self):
        part={'blocks':[], 'events':[[0,100,5,4,0,0,2,2,0,2]]}
        extra={'nodes':[1], 'columns':[[0,1,100,5,0,1,2152]], 'blocks':[]}
        with self.assertRaisesRegex(ValueError,'count mismatch'):apply_sizes(part,extra,0,1)

    def test_ambiguous_block_join_uses_only_structural_floor(self):
        part={'blocks':[[100],[100]], 'events':[[0,100,5,5,0,0,2,2,0,2]]}
        extra={'nodes':[1], 'columns':[], 'blocks':[[0,1,100,1,5000]]}
        apply_sizes(part,extra,0,1)
        self.assertEqual(part['events'][0][8:], [1848,0])


if __name__=='__main__':unittest.main()
