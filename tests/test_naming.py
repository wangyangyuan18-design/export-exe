import sys
import unittest
sys.path.insert(0, '.')
from odn_export.naming import strip_count_suffix, parse_subbox_name, subbox_sort_key
from odn_export.kmz_tree import classify_layer, home_passed_key, HOME_PASSED_NAMES

class NamingTests(unittest.TestCase):
    def test_strip_count_suffix(self):
        self.assertEqual(strip_count_suffix('Poles=374'), 'Poles')
        self.assertEqual(strip_count_suffix('New Pole=326'), 'New Pole')
        self.assertEqual(strip_count_suffix('SUB BOX(70/30)'), 'SUB BOX(70/30)')

    def test_parse_subbox(self):
        self.assertEqual(parse_subbox_name('KIM-HB09L4S4'), ('KIM-HB09', 4, 4))
        self.assertEqual(parse_subbox_name('KIM-HB09L4S4=14'), ('KIM-HB09', 4, 4))
        self.assertIsNone(parse_subbox_name('KIM-HB09'))

    def test_home_passed_name_variants(self):
        aliases = ['Sdu', 'SDUS', 'Mdu', 'MDUS', 'Church', 'Churches',
                   'Commercial', 'Commercials', 'Hospital', 'Hospitals',
                   'Institution', 'Institutions']
        canonical = {home_passed_key(name) for name in aliases}
        self.assertEqual(canonical, HOME_PASSED_NAMES)

    def test_kmz_layer_classification(self):
        self.assertEqual(classify_layer('New Pole 8m=304', ('Poles=374', 'New Pole=326')), 'pole')
        self.assertEqual(classify_layer('Exsiting Pole 10m=8', ('Poles=374', 'Exsiting Pole=48')), 'pole')
        self.assertEqual(classify_layer('SUB BOX(70/30)=8', ('KWG-HB01', 'SUB BOX=14')), 'sub_box')
        self.assertEqual(classify_layer('Distribution Cable=14', ('KWG-HB01',)), 'distribution_cable')
        self.assertEqual(classify_layer('Sdus=196', ('KWG-HB01', 'Home Passed=196')), 'home_passed')
        self.assertEqual(classify_layer('Hospitals=1', ('KWG-HB06', 'Home Passed=230')), 'home_passed')

    def test_natural_sort(self):
        names = ['KIM-HB09L1S10', 'KIM-HB09L1S2', 'KIM-HB09L2S1', 'KIM-HB10L1S1']
        self.assertEqual(sorted(names, key=subbox_sort_key), [
            'KIM-HB09L1S2', 'KIM-HB09L1S10', 'KIM-HB09L2S1', 'KIM-HB10L1S1'
        ])

if __name__ == '__main__':
    unittest.main()
