from copy import deepcopy
import io
import zipfile
import unittest
import xml.etree.ElementTree as E
import test_ndx_overlay_native_links_20261003 as author


class IndependentReview(unittest.TestCase):
    def test_mixed_old_new_destinations_only_relationship_target_changes(self):
        raw,links=author.fixture();old=deepcopy(links)
        links[0]['target']='package-0001.xlsx';links[0]['expected_workbook_reference']['path']='D:/saved/new/package-0001.xlsx'
        result=author.m.relocate_navigation(raw,links,'D:/saved/old','D:/saved/new')
        with zipfile.ZipFile(io.BytesIO(raw)) as a,zipfile.ZipFile(io.BytesIO(result)) as b:
            changed='xl/worksheets/_rels/sheet1.xml.rels'
            for name in a.namelist():
                if name!=changed:self.assertEqual(a.read(name),b.read(name))
            aa=E.fromstring(a.read(changed));bb=E.fromstring(b.read(changed))
            self.assertEqual(len(bb),1632)
            for i,(x,y) in enumerate(zip(aa,bb)):
                attrs=dict(x.attrib);attrs['Target']=links[i]['target'];self.assertEqual(attrs,y.attrib)
        self.assertEqual(links[1:],old[1:])

    def test_prefix_sibling_absolute_and_encoded_target_are_not_allowed(self):
        raw,links=author.fixture()
        for target,expected in (('../old-evil/package-0001.xlsx','D:/saved/old-evil/package-0001.xlsx'),('D:/saved/old/package-0001.xlsx','D:/saved/old/package-0001.xlsx'),('../old/%70ackage-0001.xlsx','D:/saved/old/package-0001.xlsx')):
            bad=deepcopy(links);bad[0].update(target=target);bad[0]['expected_workbook_reference']['path']=expected
            with self.subTest(target=target),self.assertRaises(ValueError):author.m.relocate_navigation(raw,bad,'D:/saved/old','D:/saved/new')


if __name__=='__main__':unittest.main()
