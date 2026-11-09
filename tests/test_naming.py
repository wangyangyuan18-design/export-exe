import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, '.')

from odn_export.xlsx_writer import write_workbook
from odn_export.naming import strip_count_suffix, parse_subbox_name, subbox_sort_key
from odn_export.kmz_tree import classify_layer, home_passed_key, HOME_PASSED_NAMES
from odn_export.rules import cable_subbox_target, numeric_hp_value


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
        self.assertEqual({home_passed_key(name) for name in aliases}, HOME_PASSED_NAMES)

    def test_kmz_layer_classification(self):
        self.assertEqual(classify_layer('New Pole 8m=304', ('Poles=374', 'New Pole=326')), 'pole')
        self.assertEqual(classify_layer('Exsiting Pole 10m=8', ('Poles=374', 'Exsiting Pole=48')), 'pole')
        self.assertEqual(classify_layer('SUB BOX(70/30)=8', ('KWG-HB01', 'SUB BOX=14')), 'sub_box')
        self.assertEqual(classify_layer('SUB BOX(50/50)=3', ('KWG-HB01', 'SUB BOX=14')), 'sub_box')
        self.assertEqual(classify_layer('END BOX=4', ('KWG-HB01', 'SUB BOX=14')), 'sub_box')
        self.assertEqual(classify_layer('Distribution Cable=14', ('KWG-HB01',)), 'distribution_cable')
        self.assertEqual(classify_layer('Sdus=196', ('KWG-HB01', 'Home Passed=196')), 'home_passed')
        self.assertEqual(classify_layer('Hospitals=1', ('KWG-HB06', 'Home Passed=230')), 'home_passed')

    def test_cable_assignment_uses_last_subbox_endpoint(self):
        subs = ['KWG-HB01L1S1', 'KWG-HB01L1S2']
        target, hits = cable_subbox_target('KWG-HB01-KWG-HB01L1S1=150', subs)
        self.assertEqual(target, 'KWG-HB01L1S1')
        self.assertEqual(hits, ['KWG-HB01L1S1'])
        target, hits = cable_subbox_target('KWG-HB01L1S1-KWG-HB01L1S2=162', subs)
        self.assertEqual(target, 'KWG-HB01L1S2')
        self.assertEqual(hits, ['KWG-HB01L1S1', 'KWG-HB01L1S2'])
        self.assertIsNone(cable_subbox_target('KWG-HB01-NO_MATCH', subs)[0])

    def test_numeric_hp_conversion(self):
        self.assertEqual(numeric_hp_value('12'), 12)
        self.assertEqual(numeric_hp_value('1,250'), 1250)
        self.assertEqual(numeric_hp_value('2.5'), 2.5)
        with self.assertRaises(Exception):
            numeric_hp_value('Sdu')

    def test_xlsx_writer_preserves_numeric_span_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'test.xlsx')
            write_workbook(path, [['', '', 'KWG-HB01', 'L1', 149.5, 1, '', '', 'KWG-HB01L1S1', 15, 1]], [], 8)
            with zipfile.ZipFile(path) as book:
                styles = book.read('xl/styles.xml').decode('utf-8')
                sheet = book.read('xl/worksheets/sheet1.xml').decode('utf-8')
            self.assertIn('formatCode="0.0"', styles)
            self.assertIn('r="E4" s="8"', sheet)
            self.assertIn('<v>149.5</v>', sheet)

    def test_natural_sort(self):
        names = ['KIM-HB09L1S10', 'KIM-HB09L1S2', 'KIM-HB09L2S1', 'KIM-HB10L1S1']
        self.assertEqual(sorted(names, key=subbox_sort_key), [
            'KIM-HB09L1S2', 'KIM-HB09L1S10', 'KIM-HB09L2S1', 'KIM-HB10L1S1'
        ])


if __name__ == '__main__':
    unittest.main()