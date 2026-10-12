import io
import json
import math
from pathlib import Path
import tempfile
import unittest
import zipfile
import numpy as np
from gerbonara import GerberFile
from PIL import Image
from pcb_diff.core import Options,compare,render,tolerant_delta
from pcb_diff.layers import classify,discover,extract,pair_layers

HEADER = '%FSLAX45Y45*%\n%MOMM*%\n%ADD10C,1*%\nD10*\n'
def gerber(extra=''):
    return HEADER+'X200000Y300000D03*\n'+extra+'M02*'

class LayerMatchingTests(unittest.TestCase):
    def test_more_than_four_layers_and_common_names(self):
        self.assertEqual(classify(Path('board.G12'),gerber())[0],'copper-inner-12')
        self.assertEqual(classify(Path('board-In7_Cu.gbr'),gerber())[0],'copper-inner-7')
        self.assertEqual(classify(Path('board-F_Cu.gbr'),gerber())[0],'copper-top')
        self.assertEqual(classify(Path('board-B_Cu.gbr'),gerber())[0],'copper-bottom')
        self.assertEqual(classify(Path('board-Edge_Cuts.gbr'),gerber())[0],'outline')

    def test_metadata_precedes_filename(self):
        code='%TF.FileFunction,Copper,L4,Inr*%\n'+gerber()
        self.assertEqual(classify(Path('misleading.GTL'),code)[0],'copper-inner-3')
        self.assertEqual(classify(Path('plain.gbr'),'%TF.FileFunction,Copper,L8,Bot*%\n'+gerber())[0],'copper-bottom')

    def test_duplicate_missing_unknown_and_manual_map(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); a=root/'a'; b=root/'b'; a.mkdir(); b.mkdir()
            (a/'board.GTL').write_text(gerber()); (b/'board.GTL').write_text(gerber())
            (a/'board.G3').write_text(gerber())
            with self.assertRaisesRegex(ValueError,'Unpaired'):
                pair_layers(a,b,False,'copper','error')
            pairs,ignored,_=pair_layers(a,b,False,'copper','skip')
            self.assertEqual(len(pairs),1); self.assertEqual(len(ignored['old']),1)
            pairs,_,_=pair_layers(a,b,False,'copper','empty')
            self.assertIsNone(pairs[1].new)
            (a/'duplicate-F_Cu.gbr').write_text(gerber())
            with self.assertRaisesRegex(ValueError,'Ambiguous'): discover(a)
            mapping=root/'map.json'
            mapping.write_text(json.dumps({'layers':[{'name':'Chosen top','old':'board.GTL','new':'board.GTL'}]}))
            pairs,_,_=pair_layers(a,b,False,'copper','error',mapping)
            self.assertEqual(len(pairs),1)
            (a/'duplicate-F_Cu.gbr').unlink()
            (a/'unknown.gbr').write_text(gerber())
            with self.assertRaisesRegex(ValueError,'unknown roles'):
                pair_layers(a,b,False,'copper','skip')

    def test_archive_signature_and_path_check(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            archive=root/'zip-named.rar'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('nested/top.GTL',gerber())
            directory,single=extract(archive,root/'unpacked')
            self.assertFalse(single); self.assertTrue((directory/'nested/top.GTL').is_file())
            archive=root/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape.GTL',gerber())
            with self.assertRaisesRegex(ValueError,'Unsafe'): extract(archive,root/'bad')

class RasterTests(unittest.TestCase):
    def test_scale_placement_repeat_and_clear_polarity(self):
        layer=GerberFile.from_string(gerber())
        a=render(layer,((0,0),(10,10)),500,500)
        self.assertTrue(np.array_equal(a,render(layer,((0,0),(10,10)),500,500)))
        self.assertAlmostEqual(a.sum()/2500,math.pi/4,delta=.025)
        ys,xs=np.where(a)
        self.assertAlmostEqual(xs.mean(),99.5,delta=.6)
        self.assertAlmostEqual(ys.mean(),349.5,delta=.6)
        cut=GerberFile.from_string(gerber('%ADD11C,0.5*%\n%LPC*%\nD11*\nX200000Y300000D03*\n'))
        c=render(cut,((0,0),(10,10)),500,500)
        self.assertFalse(np.any(c & ~a))
        self.assertAlmostEqual((a & ~c).sum()/2500,math.pi/16,delta=.02)

    def test_tolerance_exact_empty_and_distance(self):
        old=np.zeros((10,10),bool); old[3,3]=True
        new=old.copy(); new[3,4]=True; new[4,4]=True
        added,removed=tolerant_delta(old,new,1)
        self.assertFalse(added[3,4]); self.assertTrue(added[4,4]); self.assertFalse(removed.any())
        a,r=tolerant_delta(np.zeros_like(old),new,4)
        self.assertTrue(np.array_equal(a,new)); self.assertFalse(r.any())
        a,r=tolerant_delta(old,new,0)
        self.assertEqual(a.sum(),2)

class PipelineTests(unittest.TestCase):
    def test_single_files_outputs_area_report_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); a=root/'a.gbr'; b=root/'b.gbr'
            a.write_text(gerber()); b.write_text(gerber('X700000Y600000D03*\n'))
            output=root/'output'
            report=compare(a,b,output,Options(tolerance_mm=0,max_crops=0),progress=lambda _:None)
            row=report['layers'][0]
            self.assertAlmostEqual(row['exact_added_mm2'],math.pi/4,delta=.025)
            self.assertEqual(row['exact_removed_mm2'],0)
            self.assertTrue((output/'overview-exact.png').is_file())
            self.assertTrue((output/'report.html').is_file())
            with Image.open(output/'layer-old.png') as image:
                self.assertEqual(list(image.size),report['canvas_pixels'])
            self.assertEqual(json.loads((output/'results.json').read_text())['schema_version'],1)
            with self.assertRaisesRegex(ValueError,'new or empty'): compare(a,b,output,progress=lambda _:None)

    def test_explicit_offset_and_identical_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); a=root/'a.gbr'; b=root/'b.gbr'
            a.write_text(gerber()); b.write_text(HEADER+'X300000Y300000D03*\nM02*')
            report=compare(a,b,root/'aligned',Options(new_offset_mm=(-1,0)),progress=lambda _:None)
            self.assertEqual(report['layers'][0]['exact_added_mm2'],0)
            self.assertEqual(report['layers'][0]['exact_removed_mm2'],0)
            report=compare(a,a,root/'same',progress=lambda _:None)
            self.assertEqual(report['layers'][0]['exact_added_mm2'],0)

    def test_all_scope_and_empty_layer_missing_policy(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); a=root/'a'; b=root/'b'; a.mkdir(); b.mkdir()
            for directory in (a,b):
                (directory/'board.GTL').write_text(gerber())
                (directory/'board.GTS').write_text(gerber())
            (b/'board.G9').write_text(gerber())
            report=compare(a,b,root/'output',Options(scope='all',missing='empty',dpmm=10),progress=lambda _:None)
            self.assertEqual(len(report['layers']),3)
            row=next(x for x in report['layers'] if x['key']=='copper-inner-9')
            self.assertIsNone(row['old_file']); self.assertGreater(row['exact_added_mm2'],0)

    def test_size_limit_fails_without_publishing_partial_results(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); a=root/'a.gbr'; a.write_text(gerber())
            output=root/'output'
            with self.assertRaisesRegex(ValueError,'above'):
                compare(a,a,output,Options(max_megapixels=.0001),progress=lambda _:None)
            self.assertFalse(output.exists())

if __name__=='__main__': unittest.main()
