import sys
import unittest
sys.path.insert(0, '.')
from odn_export.naming import strip_count_suffix, parse_subbox_name, subbox_sort_key

class NamingTests(unittest.TestCase):
    def test_strip_count_suffix(self):
        self.assertEqual(strip_count_suffix('Poles=374'), 'Poles')
        self.assertEqual(strip_count_suffix('New Pole=326'), 'New Pole')
        self.assertEqual(strip_count_suffix('SUB BOX(70/30)'), 'SUB BOX(70/30)')

    def test_parse_subbox(self):
        self.assertEqual(parse_subbox_name('KIM-HB09L4S4'), ('KIM-HB09', 4, 4))
        self.assertEqual(parse_subbox_name('KIM-HB09L4S4=14'), ('KIM-HB09', 4, 4))
        self.assertIsNone(parse_subbox_name('KIM-HB09'))

    def test_natural_sort(self):
        names = ['KIM-HB09L1S10', 'KIM-HB09L1S2', 'KIM-HB09L2S1', 'KIM-HB10L1S1']
        self.assertEqual(sorted(names, key=subbox_sort_key), [
            'KIM-HB09L1S2', 'KIM-HB09L1S10', 'KIM-HB09L2S1', 'KIM-HB10L1S1'
        ])

if __name__ == '__main__':
    unittest.main()
