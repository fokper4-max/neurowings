import os,sys,unittest,tempfile
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen';sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import torch
from PyQt5.QtWidgets import QApplication
app=QApplication([])
from neurowings.core.data_models import *
from neurowings.core.tps_io import *
from neurowings.core.calculations import *
from neurowings.core.image_io import image_size
from neurowings.core.update_manager import *
from neurowings.ui.analysis_widget import AnalysisWidget
class Regression(unittest.TestCase):
 def test_atomic_unicode_precision_empty(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'data.tps';d=ImageData(Path('bee_🐝.jpg'),wings=[Wing(points=[WingPoint(i+.25,i+.75) for i in range(8)])],height=100,width=100)
   save_tps_from_image(d,p);load_tps_into_image(d,p);self.assertEqual(d.wings[0].points[0].x,.25)
   d.wings=[];save_tps_from_image(d,p);load_tps_into_image(d,p);self.assertEqual(d.wings,[])
 def test_bad_block(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'bad.tps';p.write_text('LM=8\nbad row\n');d=ImageData(Path('a.jpg'),width=100,height=100)
   with self.assertRaises(ValueError):load_tps_into_image(d,p)
 def test_stats(self):
  self.assertEqual(calculate_hybridization_score([10,10],'Mellifera','CI'),0)
  self.assertEqual(calculate_hybridization_score([0,0],'Mellifera','DsA'),3)
  self.assertEqual(calculate_breed_probability([1.5]*2,[-4]*2,[.8]*2,'Mellifera'),1)
 def test_aggregate(self):
  w=Wing(points=[WingPoint(x,y) for x,y in [(1161,2838),(1810,2789),(1430,2787),(1244,2791),(1422,2668),(1506,2623),(1556,2628),(1404,2497)]]);w.analyze();a=AnalysisWidget();a.update_statistics([w]);self.assertEqual(a.results_table.rowCount(),1)
 def test_updater(self):
  self.assertFalse(is_direct_download_url('http://example.com/a.exe'));self.assertFalse(is_newer_version('2.0.4rc1','2.0.4'))
 def test_exif(self):
  
  from PIL import Image
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'rotated.jpg';image=Image.new('RGB',(64,32));exif=Image.Exif();exif[274]=8;image.save(p,exif=exif);self.assertEqual(image_size(p),(32,64))
 def test_lossless_project(self):
  from neurowings.core.project_io import save_project,load_project
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/'a.tps';wing=Wing(points=[WingPoint(i+.25,i+.75,True) for i in range(8)],point_sources=['manual']*8)
   data=ImageData(Path('a.jpg'),wings=[wing],width=100,height=100)
   save_tps_from_image(data,path);save_project(data,path)
   restored=ImageData(Path('a.jpg'));self.assertTrue(load_project(restored,path));self.assertTrue(restored.wings[0].points[0].is_manual)
   path.write_text('LM=0');self.assertFalse(load_project(restored,path))
 def test_crop_center(self):
  import numpy as np
  from neurowings.workers.processing import ProcessingWorker
  worker=ProcessingWorker([],None,None,None,'cpu')
  patch,center=worker._extract_patch(np.zeros((80,80,3),dtype=np.uint8),5,5,256,80,80)
  self.assertEqual(center,(5,5));self.assertEqual(patch.shape,(256,256,3))
 def test_bbox(self):
  from neurowings.ui.graphics_items import BBoxItem
  from PyQt5.QtCore import QPointF
  from types import SimpleNamespace
  b=BBoxItem(0,0,100,100);b._resizing=True;b._resize_handle='r';b._resize_start_rect=b.rect();b._resize_start_pos=QPointF()
  for x in [10,20]:b.mouseMoveEvent(SimpleNamespace(scenePos=lambda:QPointF(x,0),accept=lambda:None))
  self.assertEqual(b.rect().width(),120)
 def test_async_interpretation_stub(self):
  from types import SimpleNamespace as NS
  from neurowings.ui.interpretation_widget import InterpretationWidget
  import time
  class Fake:
   def with_options(self,**kw):return self
   @property
   def chat(self):return NS(completions=NS(create=lambda **kw:NS(choices=[NS(message=NS(content='<stub>'))])))
  widget=InterpretationWidget();widget.set_llm(Fake(),'stub',True);widget._last_payload={'wings':36};widget.request_llm()
  deadline=time.monotonic()+5
  while widget._request.isRunning() and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
  app.processEvents();self.assertIn('<stub>',widget.text_edit.toPlainText())
 def test_vault_contract_stub(self):
  from types import SimpleNamespace
  from unittest.mock import patch
  from neurowings.core.credential_store import write_key,read_key
  values={}
  fake=SimpleNamespace(set_password=lambda s,a,v:values.update({(s,a):v}),get_password=lambda s,a:values.get((s,a)),delete_password=lambda s,a:values.pop((s,a)),errors=SimpleNamespace(PasswordDeleteError=KeyError))
  with patch.dict(sys.modules,{'keyring':fake}):
   write_key('synthetic-test-key');self.assertEqual(read_key(),'synthetic-test-key');write_key('');self.assertEqual(read_key(),'')
 def test_no_torch_import_guard(self):
  import builtins
  from unittest.mock import patch
  original=builtins.__import__
  def blocked(name,*args,**kwargs):
   if name=='torch' or name.startswith('torch.'):raise ImportError('synthetic missing torch')
   return original(name,*args,**kwargs)
  namespace={'__name__':'models_without_torch'}
  with patch('builtins.__import__',blocked):exec(((ROOT/'neurowings/core/models.py')).read_text(),namespace)
  self.assertFalse(namespace['TORCH_AVAILABLE']);self.assertIsNone(namespace['get_device']())
 def test_invalid_geometry(self):
  valid=[(1161,2838),(1810,2789),(1430,2787),(1244,2791),(1422,2668),(1506,2623),(1556,2628),(1404,2497)]
  for bad in [[(0,0)]*8,[(i,i) for i in range(8)],[(float('nan'),0)]+valid[1:],[(5000,0)]+valid[1:]]:
   wing=Wing(points=[WingPoint(x,y) for x,y in bad]);wing.analyze(image_height=4000,image_width=3000)
   self.assertFalse(wing.analysis.is_valid);self.assertTrue(wing.analysis.invalid_reason)
  wing=Wing(points=[WingPoint(x,y) for x,y in valid]);wing.analyze(image_height=4000,image_width=3000);self.assertTrue(wing.analysis.is_valid)
 def test_display_preserves_wing_identity(self):
  from unittest.mock import patch
  from neurowings.ui.main_window import MainWindow
  with patch.object(MainWindow,'_load_models'),patch.object(MainWindow,'_load_gpt_config'):
   window=MainWindow()
  first=Wing(points=[WingPoint(i+100,i+100) for i in range(8)])
  second=Wing(points=[WingPoint(i+10,i+10) for i in range(8)])
  window.current_image=ImageData(Path('test.jpg'),wings=[first,second],width=500,height=500)
  window._update_display();self.assertIs(window.current_image.wings[0],first)
  window._set_all_points_model('stage1');self.assertEqual(first.point_sources,['stage2']*8)
  window.close()
 def test_export_does_not_touch_tps(self):
  from unittest.mock import patch
  from PyQt5.QtWidgets import QFileDialog,QMessageBox
  with tempfile.TemporaryDirectory() as t:
   photo=Path(t)/'sample.jpg';tps=photo.with_suffix('.tps');tps.write_bytes(b'original TPS')
   widget=AnalysisWidget();widget.current_data=ImageData(photo);widget.aggregate_mode=False
   target=Path(t)/'sample.xlsx'
   with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'')),patch.object(QMessageBox,'information'):
    widget._export_to_excel()
   import openpyxl
   self.assertIn('Крылья',openpyxl.load_workbook(target).sheetnames);self.assertEqual(tps.read_bytes(),b'original TPS')
   old=target.read_bytes()
   with patch.object(openpyxl.Workbook,'save',side_effect=OSError('synthetic disk failure')):
    with self.assertRaises(OSError):widget._do_export(target)
   self.assertEqual(target.read_bytes(),old)
unittest.main()
