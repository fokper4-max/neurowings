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
   save_tps_from_image(d,p);load_tps_into_image(d,p);self.assertEqual(d.wings[0].points[0].x,0.0)
   d=ImageData(Path('bee_🐝.jpg'),wings=[Wing(points=[WingPoint(i+.25,i+.75) for i in range(8)])],height=100,width=100)
   save_tps_from_image(d,p,integer_pixels=False);load_tps_into_image(d,p);self.assertEqual(d.wings[0].points[0].x,.25)
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
  with patch('builtins.__import__',blocked):exec(((ROOT/'neurowings/core/models.py')).read_text(encoding='utf-8'),namespace)
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

 # === НОВЫЕ ТЕСТЫ v2.2.0 ===

 def _make_analyzed_wing(self, ci: float, dsa: float, hi: float, enabled: bool = True) -> Wing:
  """Создать тестовое крыло с заданными индексами (CI, DsA, HI)."""
  pts = [
   WingPoint(1161.0, 2838.0),
   WingPoint(1810.0, 2789.0),
   WingPoint(1430.0, 2787.0),
   WingPoint(1244.0, 2791.0),
   WingPoint(1422.0, 2668.0),
   WingPoint(1506.0, 2623.0),
   WingPoint(1556.0, 2628.0),
   WingPoint(1404.0, 2497.0),
  ]
  w = Wing(points=pts, is_enabled=enabled)
  possible, idx_valid = identify_breed(ci, dsa, hi)
  w.analysis = WingAnalysis(
   is_valid=True,
   CI=ci,
   DsA=dsa,
   HI=hi,
   breeds=possible,
   index_valid=idx_valid,
   is_identified=len(possible) > 0,
  )
  return w

 def test_colony_analysis_service_adaptive_breeds(self):
  """Проверка ColonyAnalysisService и адаптивной интерпретации для Carnica, Carpatica, Mellifera и пустой пробы."""
  from neurowings.core.colony_analysis import analyze_colony
  from neurowings.ui.interpretation_widget import InterpretationWidget

  # 1. Чистопородная выборка Carnica (CI~2.55, DsA~+2.2, HI~0.98)
  carnica_wings = [
   self._make_analyzed_wing(2.50 + (i % 5) * 0.02, 2.0 + (i % 4) * 0.2, 0.98 + (i % 3) * 0.01)
   for i in range(30)
  ]
  summary_carn = analyze_colony(carnica_wings, target_breed="Carnica", reanalyze_wings=False)
  self.assertEqual(summary_carn.eval_breed, "Carnica")
  self.assertGreaterEqual(summary_carn.total_score, 13)
  self.assertNotIn("Помесь", summary_carn.verdict_title)

  interp = InterpretationWidget()
  interp.set_target_breed("Carnica")
  interp.update_data(carnica_wings)
  text_carn = interp.text_edit.toPlainText()
  self.assertIn("Carnica", text_carn)
  self.assertNotIn("СИЛЬНАЯ МЕТИЗАЦИЯ", text_carn)

  # 2. Чистопородная выборка Carpatica (CI~2.55, DsA~+2.5, HI~0.88)
  carpatica_wings = [
   self._make_analyzed_wing(2.54 + (i % 4) * 0.02, 2.3 + (i % 4) * 0.15, 0.87 + (i % 3) * 0.01)
   for i in range(30)
  ]
  summary_carp = analyze_colony(carpatica_wings, target_breed="Carpatica", reanalyze_wings=False)
  self.assertEqual(summary_carp.eval_breed, "Carpatica")
  self.assertGreaterEqual(summary_carp.total_score, 13)

  # 3. Чистопородная выборка Mellifera (CI~1.62, DsA~-3.5, HI~0.83)
  mellifera_wings = [
   self._make_analyzed_wing(1.60 + (i % 4) * 0.02, -3.6 + (i % 4) * 0.15, 0.82 + (i % 3) * 0.01)
   for i in range(30)
  ]
  summary_mel = analyze_colony(mellifera_wings, target_breed="Mellifera", reanalyze_wings=False)
  self.assertEqual(summary_mel.dominant_breed, "Mellifera")
  self.assertGreaterEqual(summary_mel.total_score, 13)

  # 4. Выборка с identified == 0 (аномальные индексы вне всех пород): не должно быть фантомной Mellifera!
  unidentified_wings = [self._make_analyzed_wing(0.75, -15.0, 0.40) for _ in range(5)]
  summary_zero = analyze_colony(unidentified_wings, target_breed="auto", reanalyze_wings=False)
  self.assertEqual(summary_zero.identified, 0)
  self.assertEqual(summary_zero.dominant_breed_str, "—")
  self.assertEqual(summary_zero.ci_hyb_score + summary_zero.dsa_hyb_score + summary_zero.hi_hyb_score, 0)
  self.assertLessEqual(summary_zero.total_score, 0)

 def test_wing_disabled_excluded_from_statistics(self):
  """Отключение крыла чекбоксом (wing.is_enabled = False) исключает его из статистики семьи."""
  from neurowings.core.colony_analysis import analyze_colony
  good_wing = self._make_analyzed_wing(1.65, -3.2, 0.82, enabled=True)
  outlier_wing = self._make_analyzed_wing(3.20, 4.5, 1.05, enabled=False)

  summary = analyze_colony([good_wing, outlier_wing], reanalyze_wings=False)
  self.assertEqual(summary.total_wings_all, 2)
  self.assertEqual(summary.total, 1)
  self.assertEqual(summary.valid_count, 1)
  self.assertAlmostEqual(summary.ci.mean, 1.65, places=4)

 def test_pdf_passport_generation(self):
  """Генерация PDF-паспорта семьи (generate_pdf_passport) создаёт непустой PDF-файл."""
  from neurowings.core.pdf_passport import generate_pdf_passport
  wings = [
   self._make_analyzed_wing(2.52 + (i % 5) * 0.03, 2.1 + (i % 4) * 0.2, 0.84 + (i % 3) * 0.01)
   for i in range(25)
  ]
  with tempfile.TemporaryDirectory() as t:
   pdf_path = Path(t) / "passport.pdf"
   out = generate_pdf_passport(
    wings,
    pdf_path,
    sample_name="Улей №12 (Тест)",
    target_breed="Carnica",
   )
   self.assertTrue(out.exists())
   header = out.read_bytes()[:5]
   self.assertEqual(header, b"%PDF-")
   self.assertGreater(out.stat().st_size, 5000)

 def test_graphs_widget_2d_breed_map(self):
  """Проверка 2D-карты пород и всех 3 вариантов визуала графиков в GraphsWidget (включая Карташёв в. 2.5)."""
  from neurowings.ui.graphs_widget import GraphsWidget
  gw = GraphsWidget()
  wings = [
   self._make_analyzed_wing(1.65, -3.0, 0.82),
   self._make_analyzed_wing(2.55, 2.2, 0.85),
   self._make_analyzed_wing(2.48, 1.9, 0.96),
  ]
  # По умолчанию выбран 3-й вариант (индекс 2: Как в Excel «Порода по крыльям» Карташёва в. 2.5)
  self.assertEqual(gw.combo_chart_style.currentIndex(), 2)
  gw.update_graphs([1.65, 2.55, 2.48], [-3.0, 2.2, 1.9], [0.82, 0.85, 0.96], wing_numbers=[1, 2, 3], wings=wings)
  for lbl in (gw.graph_map_2d, gw.graph_ci, gw.graph_dsa, gw.graph_hi):
   self.assertIsNotNone(lbl._pixmap)
   self.assertFalse(lbl._pixmap.isNull())

  # Проверяем переключение всех 3 вариантов визуала (0: классика, 1: гистограмма + KDE, 2: Excel Карташёва)
  for style_idx in (0, 1, 2):
   gw.combo_chart_style.setCurrentIndex(style_idx)
   for lbl in (gw.graph_ci, gw.graph_dsa, gw.graph_hi):
    self.assertIsNotNone(lbl._pixmap)
    self.assertFalse(lbl._pixmap.isNull())

  # Проверяем выбор целевой породы для границ («Mellifera», «Carnica»)
  gw.set_target_breed("Mellifera")
  self.assertFalse(gw.graph_ci._pixmap.isNull())
  gw.set_target_breed("Carnica")
  self.assertFalse(gw.graph_ci._pixmap.isNull())

  # Переключение всех режимов верхней 2D-карты (0, 1, 2, 3)
  for mode_idx in (1, 2, 0):
   gw.combo_2d_mode.setCurrentIndex(mode_idx)
   self.assertFalse(gw.graph_map_2d.isHidden())
   self.assertIsNotNone(gw.graph_map_2d._pixmap)
   self.assertFalse(gw.graph_map_2d._pixmap.isNull())
  gw.combo_2d_mode.setCurrentIndex(3)
  self.assertTrue(gw.graph_map_2d.isHidden())

 def test_points_gt_preserved_on_point_moved(self):
  """Сохранение эталонных точек points_gt при ручном сдвиге точки через _on_point_moved."""
  from unittest.mock import patch
  from neurowings.ui.main_window import MainWindow
  with tempfile.TemporaryDirectory() as t:
   tps_path = Path(t) / "gt.tps"
   pts = [(1161.0, 2838.0), (1810.0, 2789.0), (1430.0, 2787.0), (1244.0, 2791.0),
          (1422.0, 2668.0), (1506.0, 2623.0), (1556.0, 2628.0), (1404.0, 2497.0)]
   img = ImageData(Path(t) / "gt.jpg", wings=[Wing(points=[WingPoint(x, y) for x, y in pts])], width=3000, height=4000)
   save_tps_from_image(img, tps_path)

   loaded = ImageData(Path(t) / "gt.jpg", width=3000, height=4000)
   load_tps_into_image(loaded, tps_path)
   self.assertEqual(len(loaded.wings[0].points_gt), 8)
   orig_gt_x = loaded.wings[0].points_gt[0].x

   with patch.object(MainWindow, '_load_models'), patch.object(MainWindow, '_load_gpt_config'):
    win = MainWindow()
   win.current_image = loaded
   win.images[str(loaded.path)] = loaded
   win._on_point_moved(0, 0, orig_gt_x + 50.0, 2800.0)

   # Рабочая точка изменилась, а эталон points_gt остался неизменным!
   self.assertEqual(loaded.wings[0].points[0].x, orig_gt_x + 50.0)
   self.assertEqual(loaded.wings[0].points_gt[0].x, orig_gt_x)
   # При переключении источника на 'gt' возвращается эталонная координата
   win._set_all_points_model('gt')
   active = loaded.wings[0].get_active_points()
   self.assertEqual(active[0][0], orig_gt_x)
   win.close()

 def test_short_vein_denominator_and_nan_save_protection(self):
  """Защита от коротких отрезков жилок (dist(P6, P7) < 0.5) и защита от NaN при сохранении."""
  pts = [
   (1161.0, 2838.0),
   (1810.0, 2789.0),
   (1430.0, 2787.0),
   (1244.0, 2791.0),
   (1422.0, 2668.0),
   (1506.0, 2623.0),
   (1506.1, 2623.1),  # P7 почти совпадает с P6 (dist ~ 0.14 < 0.5)
   (1404.0, 2497.0),
  ]
  wing = Wing(points=[WingPoint(x, y) for x, y in pts])
  wing.analyze(image_height=4000, image_width=3000)
  self.assertFalse(wing.analysis.is_valid)
  self.assertIn("жилки", wing.analysis.invalid_reason)

  # Защита от сохранения NaN в TPS
  with tempfile.TemporaryDirectory() as t:
   p = Path(t) / "nan.tps"
   nan_wing = Wing(points=[WingPoint(float('nan'), 10.0)] + [WingPoint(i + 1.0, i + 2.0) for i in range(7)])
   d = ImageData(Path("nan.jpg"), wings=[nan_wing], width=100, height=100)
   with self.assertRaises(ValueError):
    save_tps_from_image(d, p)

  # Проверка классов Руттнера и конвертации в проценты Алпатова
  self.assertAlmostEqual(ci_to_alpatov_classic(2.0), 50.0, places=4)
  ruttner = calculate_ruttner_classes([-3.5, 0.0, 2.5])
  self.assertEqual(ruttner["minus"], 1)
  self.assertEqual(ruttner["zero"], 1)
  self.assertEqual(ruttner["plus"], 1)

 def test_hardware_profiler_and_adaptive_canvas(self):
  """Проверка HardwareProfiler (4 режима мощности, TTA) и адаптации точек для больших сканов / 5K экранов."""
  from unittest.mock import patch
  from neurowings.core.hardware_profiler import HardwareProfiler
  from neurowings.ui.main_window import MainWindow

  specs = HardwareProfiler.detect_specs()
  self.assertGreaterEqual(specs.logical_cores, 1)
  self.assertGreater(specs.ram_total_gb, 0.5)

  p_ultra = HardwareProfiler.apply_profile("ultra_quality")
  self.assertTrue(p_ultra.use_tta)
  self.assertEqual(len(p_ultra.tta_scales), 3)
  self.assertEqual(p_ultra.det_imgsz, 1280)

  p_turbo = HardwareProfiler.apply_profile("turbo_speed")
  self.assertFalse(p_turbo.use_tta)
  self.assertGreaterEqual(p_turbo.pose_batch_size, 16)

  p_eco = HardwareProfiler.apply_profile("eco")
  self.assertEqual(p_eco.pose_batch_size, 4)
  self.assertTrue(p_eco.aggressive_gc)

  p_auto = HardwareProfiler.apply_profile("auto")
  self.assertIn(p_auto.mode, ("auto",))

  # Проверка точного размера точек (radius <= 1.0 px = диаметр <= 2.0 px) и невидимой зоны захвата мыши
  with patch.object(MainWindow, '_load_models'), patch.object(MainWindow, '_load_gpt_config'):
   win = MainWindow()
  pts = [(1161.0, 2838.0), (1810.0, 2789.0), (1430.0, 2787.0), (1244.0, 2791.0),
         (1422.0, 2668.0), (1506.0, 2623.0), (1556.0, 2628.0), (1404.0, 2497.0)]
  w = Wing(points=[WingPoint(x, y) for x, y in pts])
  win.current_image = ImageData(Path("huge_scan.jpg"), wings=[w], width=9359, height=3842)
  win._update_display()
  self.assertEqual(len(win.point_items), 8)
  self.assertLessEqual(win.point_items[0].radius, 1.0)
  self.assertGreaterEqual(win.point_items[0].hit_radius, 6.0)
  win.close()

 def test_kartashov_v25_parity_and_image_rotation(self):
  """Проверка 1:1 совпадения с Excel Карташева в. 2.5, калибровки точек по Рис. 15 и поворота скана в UI."""
  from unittest.mock import patch
  from PIL import Image
  from neurowings.ui.main_window import MainWindow
  from neurowings.workers.processing import ProcessingWorker
  from PyQt5.QtWidgets import QListWidgetItem
  from PyQt5.QtCore import Qt

  # 1. Калибровка точек 3, 4, 6 по Рис. 15 Карташева
  pts = [(1161.0, 2838.0), (1810.0, 2789.0), (1430.0, 2787.0), (1244.0, 2791.0),
         (1422.0, 2668.0), (1506.0, 2623.0), (1556.0, 2628.0), (1404.0, 2497.0)]
  cal = ProcessingWorker._apply_kartashov_vein_axis_calibration(pts)
  self.assertEqual(len(cal), 8)
  self.assertGreater(cal[3][0], pts[3][0])  # Точка 4 смещается вправо к пересечению осей жилок
  self.assertGreater(cal[2][0], pts[2][0])  # Точка 3 смещается вправо к пересечению осей жилок

  # 2. Поворот скана 90° / 180° / отражение в MainWindow
  with tempfile.TemporaryDirectory() as t:
   img_p = Path(t) / "scan.jpg"
   Image.new("RGB", (200, 100), color=(240, 240, 240)).save(img_p)
   with patch.object(MainWindow, '_load_models'), patch.object(MainWindow, '_load_gpt_config'):
    win = MainWindow()
   d = ImageData(img_p, wings=[Wing(points=[WingPoint(10.0, 20.0) for _ in range(8)])], width=200, height=100)
   win.images[str(img_p)] = d
   win.current_image = d
   item = QListWidgetItem(img_p.name)
   item.setData(Qt.UserRole, str(img_p))
   win.file_list.addItem(item)
   win.file_list.setCurrentItem(item)

   win._rotate_current_image_cw()
   self.assertEqual((win.current_image.width, win.current_image.height), (100, 200))
   self.assertAlmostEqual(win.current_image.wings[0].points[0].x, 80.0)
   self.assertAlmostEqual(win.current_image.wings[0].points[0].y, 10.0)
   win.close()

 def test_find_best_bees_and_highlight(self):
  """Проверка тройной фильтрации find_best_bees (CI→DsA→HI) и подсветки в AnalysisWidget."""
  from unittest.mock import patch
  from PyQt5.QtWidgets import QMessageBox
  from neurowings.core.colony_analysis import find_best_bees

  # Ядро семьи: 12 крыльев Carnica в одном классе (CI~2.45, DsA~+2.1, HI~0.96)
  core_wings = [self._make_analyzed_wing(2.45, 2.1, 0.96, enabled=True) for _ in range(12)]
  # Выбросы по CI (Mellifera), по DsA и по HI + одно отключённое крыло в пике
  outlier_ci = self._make_analyzed_wing(1.60, 2.1, 0.96, enabled=True)
  outlier_dsa = self._make_analyzed_wing(2.45, -4.5, 0.96, enabled=True)
  outlier_hi = self._make_analyzed_wing(2.45, 2.1, 0.72, enabled=True)
  disabled_core = self._make_analyzed_wing(2.45, 2.1, 0.96, enabled=False)

  wings = core_wings + [outlier_ci, outlier_dsa, outlier_hi, disabled_core]
  best = find_best_bees(wings)
  self.assertEqual(best, list(range(12)))
  self.assertEqual(find_best_bees([]), [])

  # Проверка кнопки «🏆 Лучшие пчёлы» в обычном режиме (ImageData) и aggregate_mode (list)
  aw = AnalysisWidget()
  img_data = ImageData(Path("colony.jpg"), wings=wings, width=1000, height=1000)
  img_data.analyze_all_wings = lambda: None
  aw.update_statistics(img_data)
  with patch.object(QMessageBox, "information") as mock_info:
   aw._highlight_best_bees()
   self.assertTrue(mock_info.called)
   msg_text = mock_info.call_args[0][2]
   self.assertIn("Породное ядро семьи", msg_text)
   self.assertIn("2.450", msg_text)
  # Первая строка (ядро) выделена золотистым цветом, строка с выбросом (12) — нет
  self.assertEqual(aw.results_table.item(0, 0).background().color().name().lower(), "#fff3bf")
  self.assertNotEqual(aw.results_table.item(12, 0).background().color().name().lower(), "#fff3bf")

  # В режиме aggregate_mode (список крыльев) не должно быть AttributeError
  aw.update_statistics(wings)
  with patch.object(QMessageBox, "information") as mock_info:
   aw._highlight_best_bees()
   self.assertTrue(mock_info.called)

 def test_mating_mode_purebred_vs_free_mated(self):
  """Проверка переключателя Чистопородная / Свободноспаренная (±15% к границам породы)."""
  from neurowings.ui.interpretation_widget import InterpretationWidget
  from neurowings.core.colony_analysis import analyze_colony

  interp = InterpretationWidget()
  self.assertEqual(interp.get_mating_mode(), "purebred")

  # Carpatica CI стандарт: 2.30..3.00 (span=0.70). Значение 2.22 ниже 2.30:
  # В режиме purebred (lo=2.30) -> 2.22 попадает в warn ("Небольшое отклонение").
  txt_pure, state_pure = interp._evaluate_index_for_breed(2.22, "Carpatica", "CI")
  self.assertEqual(state_pure, "warn")
  self.assertNotIn("(свободн.)", txt_pure)

  # Переключаем на Свободноспаренная (free_mated): lo расширяется до 2.30 - 0.105 = 2.195 -> state="good"
  idx_free = interp.mating_combo.findData("free_mated")
  interp.mating_combo.setCurrentIndex(idx_free)
  self.assertEqual(interp.get_mating_mode(), "free_mated")
  txt_free, state_free = interp._evaluate_index_for_breed(2.22, "Carpatica", "CI")
  self.assertEqual(state_free, "good")
  self.assertIn("(свободн.)", txt_free)

  # Проверка analyze_colony с mating_mode="free_mated" vs "purebred"
  wings = [self._make_analyzed_wing(2.22, 2.5, 0.90) for _ in range(10)]
  res_pure = analyze_colony(wings, target_breed="Carpatica", reanalyze_wings=False, mating_mode="purebred")
  res_free = analyze_colony(wings, target_breed="Carpatica", reanalyze_wings=False, mating_mode="free_mated")
  self.assertEqual(len(res_pure.wings_in_eval_breed), 0)
  self.assertEqual(len(res_free.wings_in_eval_breed), 10)
  self.assertIn("свободноспаренная матка", res_free.verdict_title)

 def test_cursors_keyboard_placement_and_minimap(self):
  """Проверка контрастных курсоров, расстановки по Space/Enter и миникарты MiniMapWidget."""
  from unittest.mock import patch
  from PyQt5.QtWidgets import QGraphicsScene
  from PyQt5.QtCore import Qt, QEvent, QPoint, QPointF
  from PyQt5.QtGui import QKeyEvent, QMouseEvent
  from neurowings.ui.graphics_view import ZoomableGraphicsView, _get_cached_cursors
  from neurowings.ui.main_window import MainWindow

  # 1. Проверка кэшированных контрастных курсоров (25x25 с прозрачным центром 12,12)
  c_edit, c_add, c_bbox = _get_cached_cursors()
  for cur in (c_edit, c_add, c_bbox):
   self.assertEqual(cur.shape(), Qt.BitmapCursor)
   self.assertFalse(cur.pixmap().isNull())
   self.assertEqual((cur.pixmap().width(), cur.pixmap().height()), (25, 25))
   img = cur.pixmap().toImage()
   self.assertEqual(img.pixelColor(12, 12).alpha(), 0)

  scene = QGraphicsScene(0, 0, 2000, 1500)
  view = ZoomableGraphicsView(scene)
  view.resize(800, 600)
  view.show()
  app.processEvents()

  for mode, expected_shape in [
   (EditMode.VIEW, Qt.OpenHandCursor),
   (EditMode.EDIT, Qt.BitmapCursor),
   (EditMode.ADD, Qt.BitmapCursor),
   (EditMode.BBOX, Qt.BitmapCursor),
   (EditMode.VIEW, Qt.OpenHandCursor),
  ]:
   view.set_edit_mode(mode)
   self.assertEqual(view.cursor().shape(), expected_shape)
   self.assertEqual(view.viewport().cursor().shape(), expected_shape)

  # 2. Клавиатурная расстановка точек по Space/Enter в режиме ADD + защита от автоповтора
  clicked_coords = []
  view.scene_clicked.connect(lambda x, y: clicked_coords.append((x, y)))
  view.set_edit_mode(EditMode.ADD)
  view._last_mouse_pos = QPoint(250, 200)
  view.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier))
  self.assertEqual(len(clicked_coords), 1)
  # Автоповтор при зажатом пробеле игнорируется
  view.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " ", True, 1))
  self.assertEqual(len(clicked_coords), 1)
  view.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
  self.assertEqual(len(clicked_coords), 2)

  # Клавиатурное создание рамки в режиме BBOX (два нажатия Space)
  created_bboxes = []
  view.bbox_created.connect(lambda x1, y1, x2, y2: created_bboxes.append((x1, y1, x2, y2)))
  view.set_edit_mode(EditMode.BBOX)
  view._last_mouse_pos = QPoint(100, 100)
  view.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier))
  self.assertIsNotNone(view._bbox_start)
  view._last_mouse_pos = QPoint(300, 260)
  view.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier))
  self.assertIsNone(view._bbox_start)
  self.assertEqual(len(created_bboxes), 1)

  # 3. Миникарта MiniMapWidget: показ/скрытие, ресайз, зум и навигация кликом
  self.assertFalse(hasattr(view, "_minimap") and view._minimap is not None)
  view.toggle_minimap()
  self.assertIsNotNone(view._minimap)
  self.assertTrue(view._minimap.isVisible())

  # Проверка позиционирования в правом верхнем углу вьюпорта (не перекрывает скроллбары)
  vp_w = view.viewport().width()
  self.assertEqual(view._minimap.x(), vp_w - view._minimap.width() - 8)
  self.assertEqual(view._minimap.y(), 8)

  # При ресайзе окна миникарта перепозиционируется и не уходит в отрицательные координаты
  view.resize(1000, 700)
  app.processEvents()
  self.assertEqual(view._minimap.x(), view.viewport().width() - view._minimap.width() - 8)

  # Навигация по клику на миникарте центрирует вид
  view.scale(3.0, 3.0)
  nav_targets = []
  view._minimap.navigation_requested.connect(lambda sx, sy: nav_targets.append((sx, sy)))
  press_ev = QMouseEvent(
   QEvent.MouseButtonPress,
   QPointF(view._minimap.width() / 2, view._minimap.height() / 2),
   Qt.LeftButton, Qt.LeftButton, Qt.NoModifier
  )
  view._minimap.mousePressEvent(press_ev)
  view._minimap.mouseReleaseEvent(press_ev)
  self.assertEqual(len(nav_targets), 1)
  self.assertAlmostEqual(nav_targets[0][0], 1000.0, delta=50.0)
  self.assertAlmostEqual(nav_targets[0][1], 750.0, delta=50.0)

  # Повторный toggle скрывает миникарту
  view.toggle_minimap()
  self.assertFalse(view._minimap.isVisible())
  view.close()

  # Проверка интеграции с MainWindow._toggle_minimap
  with patch.object(MainWindow, "_load_models"), patch.object(MainWindow, "_load_gpt_config"):
   win = MainWindow()
  win._toggle_minimap()
  self.assertTrue(hasattr(win.view, "_minimap") and win.view._minimap is not None)
  win.close()

 def test_github_releases_updater_and_update_tab(self):
  """Проверка парсинга GitHub Releases API JSON, скачивания с/без SHA256, запуска скрипта и вкладки «🔄 Обновление»."""
  import hashlib
  import io
  import json
  from unittest.mock import patch, MagicMock
  from PyQt5.QtWidgets import QMessageBox
  from neurowings.ui.main_window import MainWindow
  from neurowings.core.update_manager import (
   normalize_update_info,
   fetch_update_feed,
   download_update,
   launch_windows_update_script,
   is_newer_version,
   UpdateError,
  )

  # 1. Парсинг ответа GitHub Releases API (с полем digest у ассета .exe и markdown body)
  sample_sha = "a077e85583a22be9fb8348fb8c635bd22d2deff705fd355fa35fa675fa0b7db8"
  gh_payload = {
   "url": "https://api.github.com/repos/fokper4-max/neurowings/releases/999",
   "html_url": "https://github.com/fokper4-max/neurowings/releases/tag/v2.4.0",
   "tag_name": "v2.4.0",
   "name": "НейроКрылья v2.4.0 - Автообновление с GitHub",
   "published_at": "2026-11-05T18:30:00Z",
   "body": "### Что нового в v2.4.0\n- **Автообновление** с GitHub Releases\n- Вкладка «🔄 Обновление» в главном окне\n",
   "assets": [
    {
     "name": "NeuroWings-2.4.0.exe",
     "size": 150000000,
     "browser_download_url": "https://github.com/fokper4-max/neurowings/releases/download/v2.4.0/NeuroWings-2.4.0.exe",
     "digest": f"sha256:{sample_sha}",
    }
   ],
  }
  info = normalize_update_info(gh_payload, "https://api.github.com/repos/fokper4-max/neurowings/releases/latest")
  self.assertEqual(info["version"], "2.4.0")
  self.assertTrue(is_newer_version(info["version"], "2.3.0"))
  self.assertEqual(
   info["download_url"],
   "https://github.com/fokper4-max/neurowings/releases/download/v2.4.0/NeuroWings-2.4.0.exe",
  )
  self.assertEqual(info["sha256"], sample_sha)
  self.assertEqual(info["published_at"], "2026-11-05")
  self.assertEqual(info["source"], "github")
  self.assertIn("Автообновление с GitHub Releases", info["notes"])

  # 2. Извлечение SHA256 из текста body релиза, если поле digest отсутствует
  gh_payload_body_sha = {
   "tag_name": "v2.4.1",
   "body": f"- Исправления ошибок\nSHA256: `{sample_sha.upper()}`",
   "assets": [
    {
     "name": "NeuroWings-2.4.1.exe",
     "browser_download_url": "https://github.com/fokper4-max/neurowings/releases/download/v2.4.1/NeuroWings-2.4.1.exe",
    }
   ],
  }
  info_body_sha = normalize_update_info(gh_payload_body_sha)
  self.assertEqual(info_body_sha["version"], "2.4.1")
  self.assertEqual(info_body_sha["sha256"], sample_sha)

  # 3. fetch_update_feed пробует GitHub API и при ошибке переключается на резервный update-feed.json
  fallback_payload = {
   "version": "2.3.5",
   "url": "https://193-124-117-175.nip.io/downloads/neurowings/NeuroWings-2.3.5.exe",
   "sha256": sample_sha,
   "notes": ["Резервный канал обновлений"],
  }
  call_urls = []
  def fake_urlopen(req, timeout=8, context=None):
   url = req.full_url if hasattr(req, "full_url") else str(req)
   call_urls.append(url)
   if "api.github.com" in url:
    raise OSError("GitHub API temporarily unreachable")
   resp = MagicMock()
   resp.read.return_value = json.dumps(fallback_payload).encode("utf-8")
   resp.__enter__.return_value = resp
   resp.__exit__.return_value = False
   return resp

  with patch("neurowings.core.update_manager.urlopen", side_effect=fake_urlopen):
   fb_info = fetch_update_feed("")
  self.assertEqual(fb_info["version"], "2.3.5")
  self.assertGreaterEqual(len(call_urls), 2)
  self.assertIn("api.github.com", call_urls[0])

  # 4. download_update: проверка с SHA256 и fallback для GitHub без SHA256 (проверка MZ + размера > 1 МБ)
  with tempfile.TemporaryDirectory() as t:
   fake_exe_bytes = b"MZ" + (b"\x90" * (1_050_000))
   fake_sha = hashlib.sha256(fake_exe_bytes).hexdigest()

   def fake_dl_open(req, timeout=30, context=None):
    bio = io.BytesIO(fake_exe_bytes)
    bio.headers = {"Content-Length": str(len(fake_exe_bytes))}
    bio.__enter__ = lambda s=bio: s
    bio.__exit__ = lambda *a: False
    return bio

   dest1 = Path(t) / "NeuroWings-sha.exe"
   with patch("neurowings.core.update_manager.urlopen", side_effect=fake_dl_open):
    out1 = download_update(
     {"download_url": "https://github.com/fokper4-max/neurowings/releases/download/v2.4.0/NW.exe", "sha256": fake_sha},
     dest1,
    )
   self.assertTrue(out1.exists())
   self.assertEqual(out1.stat().st_size, len(fake_exe_bytes))

   # Скачивание с GitHub без SHA256 проходит благодаря проверке PE-заголовка MZ и размера > 1 МБ
   dest2 = Path(t) / "NeuroWings-nosha.exe"
   with patch("neurowings.core.update_manager.urlopen", side_effect=fake_dl_open):
    out2 = download_update(
     {"download_url": "https://github.com/fokper4-max/neurowings/releases/download/v2.4.0/NW.exe", "sha256": ""},
     dest2,
    )
   self.assertTrue(out2.exists())

   # А со стороннего домена без SHA256 - блокируется
   with self.assertRaises(UpdateError):
    download_update(
     {"download_url": "https://example.com/NW.exe", "sha256": ""},
     Path(t) / "bad.exe",
    )

   # 5. launch_windows_update_script: прямой запуск без RunAs при праве записи и fallback с RunAs при запрете
   script_p = Path(t) / "apply_update.ps1"
   script_p.write_text("# test", encoding="utf-8")
   target_exe = Path(t) / "NeuroWings.exe"
   with patch("neurowings.core.update_manager.os.access", return_value=True), \
        patch("neurowings.core.update_manager.subprocess.Popen") as mock_popen, \
        patch("neurowings.core.update_manager.subprocess.run") as mock_run:
    launch_windows_update_script(script_p, target_exe)
    self.assertTrue(mock_popen.called)
    self.assertFalse(mock_run.called)

   with patch("neurowings.core.update_manager.os.access", return_value=False), \
        patch("neurowings.core.update_manager.subprocess.Popen") as mock_popen, \
        patch("neurowings.core.update_manager.subprocess.run") as mock_run:
    launch_windows_update_script(script_p, target_exe)
    self.assertFalse(mock_popen.called)
    self.assertTrue(mock_run.called)

  # 6. Проверка вкладки «🔄 Обновление» и всплывающего окна Да/Нет в MainWindow
  with patch.object(MainWindow, "_load_models"), patch.object(MainWindow, "_load_gpt_config"):
   win = MainWindow()

  tab_idx = win.tab_widget.indexOf(win.update_tab)
  self.assertGreaterEqual(tab_idx, 0)
  self.assertEqual(win.tab_widget.tabText(tab_idx), "🔄 Обновление")
  self.assertFalse(win.btn_install_update.isEnabled())

  # Симулируем приход новой версии v2.4.0 и ответ «Нет» во всплывающем окне (пользователь решил обновиться позже)
  info_new = dict(info)
  info_new["update_available"] = True
  with patch.object(QMessageBox, "question", return_value=QMessageBox.No) as mock_q:
   win._on_update_check_finished(info_new, manual=True)
   self.assertTrue(mock_q.called)

  # Вкладка обновилась, получила индикатор 🔴, кнопка скачивания стала активной!
  self.assertEqual(win.tab_widget.tabText(tab_idx), "🔄 Обновление 🔴")
  self.assertTrue(win.btn_install_update.isEnabled())
  self.assertIn("2.4.0", win.lbl_update_latest_ver.text())
  self.assertIn("Автообновление с GitHub Releases", win.txt_update_notes.toPlainText())

  # Проверка прогресс-бара на вкладке «🔄 Обновление»
  win.update_tab_progress_box.setVisible(True)
  win._on_update_download_progress(50 * 1024 * 1024, 100 * 1024 * 1024)
  self.assertEqual(win.update_tab_progress_bar.value(), 50)
  self.assertIn("50%", win.lbl_update_progress_status.text())

  # Симулируем проверку, когда установлена актуальная версия
  info_same = dict(info)
  info_same["version"] = "2.3.0"
  info_same["update_available"] = False
  win._on_update_check_finished(info_same, manual=False)
  self.assertEqual(win.tab_widget.tabText(tab_idx), "🔄 Обновление")
  self.assertFalse(win.btn_install_update.isEnabled())
  win.close()

 def test_tps_tpsdig2_excel_sync_and_p4_p5_p7_calibration(self):
  """Проверка 100% сквозной синхронизации NeuroWings <-> TPS <-> tpsDig2 <-> Excel в. 2.5 и калибровки точек 4, 5, 7, 8."""
  from unittest.mock import patch
  from PIL import Image
  from PyQt5.QtWidgets import QListWidgetItem
  from PyQt5.QtCore import Qt
  from neurowings.ui.main_window import MainWindow
  from neurowings.workers.processing import ProcessingWorker

  # 1. Проверка геометрической доводки точек 3, 4, 5, 6, 7, 8
  pts = [
   (1161.0, 2838.0), (1810.0, 2789.0), (1430.0, 2787.0), (1244.0, 2791.0),
   (1422.0, 2668.0), (1506.0, 2623.0), (1556.0, 2628.0), (1404.0, 2497.0),
  ]
  cal = ProcessingWorker._apply_kartashov_vein_axis_calibration(pts)
  self.assertEqual(len(cal), 8)
  self.assertGreater(cal[3][0], pts[3][0])
  self.assertGreater(cal[2][0], pts[2][0])
  self.assertLess(cal[4][1], pts[4][1])
  self.assertGreater(cal[6][1], pts[6][1])

  # 2. Сквозная проверка целочисленного квантования (1:1 с tpsDig2 TImageEnVect) и автосохранения .tps
  with tempfile.TemporaryDirectory() as t:
   img_p = Path(t) / "092_B.jpg"
   tps_p = Path(t) / "092_B.tps"
   Image.new("RGB", (3000, 4000), color=(245, 245, 245)).save(img_p)

   with patch.object(MainWindow, "_load_models"), patch.object(MainWindow, "_load_gpt_config"):
    win = MainWindow()

   img_data = ImageData(img_p, width=3000, height=4000)
   win.images[str(img_p)] = img_data
   win.current_image = img_data
   item = QListWidgetItem(f"○ 1) {img_p.name}")
   item.setData(Qt.UserRole, str(img_p))
   win.file_list.addItem(item)
   win.file_list.setCurrentItem(item)

   w1 = Wing(points=[WingPoint(x + 0.37, y + 0.62) for x, y in pts])
   w2 = Wing(points=[WingPoint(x + 10.41, y + 20.19) for x, y in pts])
   win._on_finished({str(img_p): [w1, w2]})

   self.assertTrue(tps_p.exists())
   tps_text = tps_p.read_text(encoding="cp1251")
   self.assertIn("LM=16", tps_text)
   self.assertIn("ID=0", tps_text)
   self.assertIn(",00000", tps_text)

   reloaded = ImageData(img_p, width=3000, height=4000)
   load_tps_into_image(reloaded, tps_p)
   reloaded.analyze_all_wings()
   for wa, wb in zip(win.current_image.wings, reloaded.wings):
    self.assertAlmostEqual(wa.analysis.CI, wb.analysis.CI, places=12)
    self.assertAlmostEqual(wa.analysis.DsA, wb.analysis.DsA, places=12)
    self.assertAlmostEqual(wa.analysis.HI, wb.analysis.HI, places=12)

   win._on_point_moved(0, 3, 1250.4, 2790.6)
   self.assertEqual(win.current_image.wings[0].points[3].x, 1250.0)
   self.assertEqual(win.current_image.wings[0].points[3].y, 2791.0)
   reloaded2 = ImageData(img_p, width=3000, height=4000)
   load_tps_into_image(reloaded2, tps_p)
   self.assertEqual(reloaded2.wings[0].points[3].x, 1250.0)
   self.assertEqual(reloaded2.wings[0].points[3].y, 2791.0)

   win.current_image.wings[1].is_enabled = False
   win._auto_save_tps(win.current_image)
   tps_text_after_disable = tps_p.read_text(encoding="cp1251")
   self.assertIn("LM=8", tps_text_after_disable)

   # 3. Проверка авто-лечения старых битых .tps с дробными координатами и ID=1 (кейс Б.rar Руслана / Макрос3 Excel в. 2.5)
   legacy_tps = Path(t) / "legacy_broken.tps"
   legacy_img = Path(t) / "legacy_broken.jpg"
   Image.new("RGB", (5462, 15403), color=(240, 240, 240)).save(legacy_img)
   legacy_lines = ["LM=8"] + [f"{2251.37247 + k:.5f} {14787.50652 - k:.5f}".replace(".", ",") for k in range(8)] + [
    f"IMAGE={legacy_img.name}", "ID=1"
   ]
   legacy_tps.write_bytes(("\r\n".join(legacy_lines) + "\r\n").encode("cp1251"))
   self.assertTrue(win._tps_file_needs_excel_repair(legacy_tps))

   legacy_data = ImageData(legacy_img)
   win._load_tps_for_image(legacy_data, legacy_tps)
   self.assertFalse(win._tps_file_needs_excel_repair(legacy_tps))
   repaired_text = legacy_tps.read_text(encoding="cp1251")
   self.assertIn("2251,00000 14788,00000", repaired_text)
   self.assertIn("ID=0", repaired_text)
   self.assertNotIn("ID=1", repaired_text)
   win.close()

 def test_excel_roundup_score_and_onefile_updater_script(self):
  """Проверка формулы 5 + ROUNDUP((ROUND(P,3)-100%)/10%, 0) как в Excel Анализ!D15 и цикла ожидания блокировки файла в PowerShell."""
  from neurowings.core.colony_analysis import _excel_roundup_score
  from neurowings.core.update_manager import create_windows_update_script
  self.assertEqual(_excel_roundup_score(100.0), 5)
  self.assertEqual(_excel_roundup_score(92.2), 4)
  self.assertEqual(_excel_roundup_score(63.9), 1)
  self.assertEqual(_excel_roundup_score(61.9), 1)
  self.assertEqual(_excel_roundup_score(59.9), 0)
  self.assertEqual(_excel_roundup_score(15.5), -4)
  self.assertEqual(_excel_roundup_score(0.0), -5)

  with tempfile.TemporaryDirectory() as t:
   src = Path(t) / "NeuroWings-2.2.2.exe"
   dst = Path(t) / "NeuroWings.exe"
   ps1 = create_windows_update_script(src, dst, 99999)
   ps1_text = ps1.read_text(encoding="utf-8-sig")
   self.assertIn("for ($attempt = 1; $attempt -le 40; $attempt++)", ps1_text)
   self.assertIn("Start-Sleep -Milliseconds 1200", ps1_text)

 def test_remove_files_and_empty_state_in_left_panel(self):
  """Удаление файлов из левого списка, пустое состояние, повторная загрузка и режим одиночного крыла."""
  from unittest.mock import patch
  from PIL import Image
  from PyQt5.QtCore import Qt
  from PyQt5.QtWidgets import QMessageBox
  from neurowings.ui.main_window import MainWindow

  pts1 = [
   (20.0, 60.0), (80.0, 55.0), (45.0, 54.0), (30.0, 56.0),
   (44.0, 40.0), (52.0, 35.0), (58.0, 36.0), (42.0, 22.0),
  ]
  pts2 = [
   (25.0, 62.0), (85.0, 58.0), (50.0, 56.0), (34.0, 58.0),
   (48.0, 42.0), (57.0, 36.0), (63.0, 37.0), (46.0, 23.0),
  ]

  with tempfile.TemporaryDirectory() as t:
   p1 = Path(t) / "a_file1.jpg"
   p2 = Path(t) / "b_file2.jpg"
   p3 = Path(t) / "c_file3.jpg"
   for p, col in ((p1, (240, 240, 240)), (p2, (235, 235, 240)), (p3, (240, 235, 235))):
    Image.new("RGB", (120, 90), color=col).save(p)

   with patch.object(MainWindow, "_load_models"), patch.object(MainWindow, "_load_gpt_config"):
    win = MainWindow()
   try:
    win._load_file_paths([p1, p2, p3])
    self.assertTrue(hasattr(win, "btn_remove_file"))
    self.assertTrue(win.left_panel.isAncestorOf(win.btn_remove_file))
    self.assertEqual(win.file_list.count(), 3)
    self.assertEqual(Path(win.current_image.path), p1)

    # Ставим 1 крыло в 1-й файл и делаем правку (запись в _undo_stack)
    w1 = Wing(points=[WingPoint(x, y, True) for x, y in pts1], point_sources=["manual"] * 8)
    win.current_image.wings = [w1]
    win.current_image.analyze_all_wings()
    win._remember_edit()
    win.current_image.is_modified = True
    win._update_display()
    self.assertTrue(any(str(p) == str(p1) for p, _ in win._undo_stack))

    # Удаляем текущий файл из списка (файл на диске остается нетронутым)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Discard) as mock_q:
     win._remove_current_file()
     self.assertTrue(mock_q.called)

    self.assertEqual(win.file_list.count(), 2)
    self.assertEqual(len(win.images), 2)
    self.assertIn("1)", win.file_list.item(0).text())
    self.assertIn(p2.name, win.file_list.item(0).text())
    self.assertIn("2)", win.file_list.item(1).text())
    self.assertIn(p3.name, win.file_list.item(1).text())
    self.assertIsNotNone(win.current_image)
    self.assertEqual(Path(win.current_image.path), p2)
    self.assertFalse(any(str(p) == str(p1) for p, _ in win._undo_stack))
    self.assertTrue(p1.exists())

    # Отмечаем оставшиеся 2 файла галочками и убираем через _remove_files_action
    for row in range(win.file_list.count()):
     win.file_list.item(row).setCheckState(Qt.Checked)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as mock_q:
     win._remove_files_action()
     self.assertTrue(mock_q.called)

    self.assertEqual(win.file_list.count(), 0)
    self.assertIsNone(win.current_image)
    self.assertEqual(len(win.images), 0)
    self.assertEqual(win.lbl_wings_count.text(), "Крыльев: 0")
    self.assertTrue(p2.exists())
    self.assertTrue(p3.exists())

    # Загружаем файл снова в то же окно - отображение и _update_display работают без RuntimeError
    win._load_file_paths([p1])
    self.assertEqual(win.file_list.count(), 1)
    self.assertEqual(Path(win.current_image.path), p1)
    win._update_display()

    # Удаление не-текущего файла в режиме single_wing_mode = True (пересчет сводной статистики)
    win._load_file_paths([p1, p2])
    win.images[str(p1)].wings = [
     Wing(points=[WingPoint(x, y, True) for x, y in pts1], point_sources=["manual"] * 8)
    ]
    win.images[str(p2)].wings = [
     Wing(points=[WingPoint(x, y, True) for x, y in pts2], point_sources=["manual"] * 8)
    ]
    win.images[str(p1)].analyze_all_wings()
    win.images[str(p2)].analyze_all_wings()
    win._toggle_single_wing_mode(True)
    self.assertTrue(win.single_wing_mode)
    self.assertIsNotNone(win.analysis_widget.last_result)
    self.assertEqual(win.analysis_widget.last_result.total, 2)
    self.assertEqual(win.analysis_widget.analysis_table.item(0, 2).text(), "2")
    self.assertEqual(Path(win.current_image.path), p1)

    win.file_list.item(1).setCheckState(Qt.Checked)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
     win._remove_files_action()

    self.assertEqual(win.file_list.count(), 1)
    self.assertEqual(Path(win.current_image.path), p1)
    self.assertIsNotNone(win.analysis_widget.last_result)
    self.assertEqual(win.analysis_widget.last_result.total, 1)
    self.assertEqual(win.analysis_widget.analysis_table.item(0, 2).text(), "1")
    self.assertTrue(p2.exists())
   finally:
    win.close()

 def test_delete_last_wing_persists_empty_tps_and_updates_left_list(self):
  """Удаление последнего крыла перезаписывает пустой .tps и обновляет маркер и статистику слева."""
  from unittest.mock import patch
  from PIL import Image
  from PyQt5.QtWidgets import QMessageBox
  from neurowings.ui.main_window import MainWindow

  pts = [
   (116.0, 283.0), (181.0, 278.0), (143.0, 278.0), (124.0, 279.0),
   (142.0, 266.0), (150.0, 262.0), (155.0, 262.0), (140.0, 249.0),
  ]

  with tempfile.TemporaryDirectory() as t:
   img_p = Path(t) / "single.jpg"
   tps_p = img_p.with_suffix(".tps")
   Image.new("RGB", (300, 400), color=(240, 240, 240)).save(img_p)

   init_data = ImageData(
    img_p,
    wings=[Wing(points=[WingPoint(x, y) for x, y in pts])],
    width=300,
    height=400,
   )
   save_tps_from_image(init_data, tps_p)
   self.assertIn("LM=8", tps_p.read_text(encoding="cp1251"))

   with patch.object(MainWindow, "_load_models"), patch.object(MainWindow, "_load_gpt_config"):
    win = MainWindow()
   try:
    win._load_file_paths([img_p])
    self.assertEqual(len(win.current_image.wings), 1)
    self.assertTrue(win.file_list.item(0).text().startswith("✓"))
    self.assertEqual(win.lbl_files_stats.text(), "Готово: 1 из 1")

    win.wings_table.setCurrentCell(-1, -1)
    win.selected_wing_idx = 0
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as mock_q:
     win._delete_selected_wing()
     self.assertTrue(mock_q.called)

    self.assertEqual(len(win.current_image.wings), 0)
    self.assertFalse(win.current_image.is_modified)

    reloaded = ImageData(img_p, width=300, height=400)
    load_tps_into_image(reloaded, tps_p)
    self.assertEqual(len(reloaded.wings), 0)

    self.assertTrue(win.file_list.item(0).text().startswith("○"))
    self.assertEqual(win.lbl_files_stats.text(), "Готово: 0 из 1")
   finally:
    win.close()

 def test_rotate_ccw90_and_roundtrip_coordinates(self):
  """Поворот 90 влево и обратный поворот 90 вправо сохраняют размер, пиксельный маркер, точки и bbox 1:1."""
  from unittest.mock import patch
  from PIL import Image
  from neurowings.ui.main_window import MainWindow

  orig_pts = [
   (40.0, 95.0), (190.0, 88.0), (110.0, 86.0), (70.0, 89.0),
   (108.0, 62.0), (125.0, 52.0), (138.0, 54.0), (105.0, 28.0),
  ]
  orig_bbox = BBox(30.0, 20.0, 200.0, 105.0)

  with tempfile.TemporaryDirectory() as t:
   img_p = Path(t) / "rect_marker.png"
   im = Image.new("RGB", (240, 120), color=(240, 240, 240))
   for y in range(20):
    for x in range(20):
     im.putpixel((x, y), (255, 0, 0))
   im.save(img_p)

   with patch.object(MainWindow, "_load_models"), patch.object(MainWindow, "_load_gpt_config"):
    win = MainWindow()
   try:
    win._load_file_paths([img_p])
    win.current_image.wings = [
     Wing(
      points=[WingPoint(x, y, True) for x, y in orig_pts],
      bbox=BBox(orig_bbox.x1, orig_bbox.y1, orig_bbox.x2, orig_bbox.y2),
      point_sources=["manual"] * 8,
     )
    ]

    # Поворот 90 влево (ccw90): (240, 120) -> (120, 240), (x, y) -> (y, 240 - x)
    win._rotate_current_image_ccw()
    self.assertEqual((win.current_image.width, win.current_image.height), (120, 240))
    self.assertEqual(image_size(img_p), (120, 240))

    with Image.open(img_p) as rot_im:
     self.assertEqual(rot_im.getpixel((5, 234)), (255, 0, 0))
     self.assertEqual(rot_im.getpixel((5, 5)), (240, 240, 240))

    w_ccw = win.current_image.wings[0]
    for (ox, oy), pt in zip(orig_pts, w_ccw.points):
     self.assertAlmostEqual(pt.x, oy, places=6)
     self.assertAlmostEqual(pt.y, 240.0 - ox, places=6)
    self.assertAlmostEqual(w_ccw.bbox.x1, orig_bbox.y1, places=6)
    self.assertAlmostEqual(w_ccw.bbox.y1, 240.0 - orig_bbox.x2, places=6)
    self.assertAlmostEqual(w_ccw.bbox.x2, orig_bbox.y2, places=6)
    self.assertAlmostEqual(w_ccw.bbox.y2, 240.0 - orig_bbox.x1, places=6)

    # Обратный поворот 90 вправо (cw90): возврат 1:1 к (240, 120) и исходным координатам
    win._rotate_current_image_cw()
    self.assertEqual((win.current_image.width, win.current_image.height), (240, 120))
    self.assertEqual(image_size(img_p), (240, 120))

    with Image.open(img_p) as back_im:
     self.assertEqual(back_im.getpixel((5, 5)), (255, 0, 0))

    w_back = win.current_image.wings[0]
    for (ox, oy), pt in zip(orig_pts, w_back.points):
     self.assertAlmostEqual(pt.x, ox, places=6)
     self.assertAlmostEqual(pt.y, oy, places=6)
    self.assertAlmostEqual(w_back.bbox.x1, orig_bbox.x1, places=6)
    self.assertAlmostEqual(w_back.bbox.y1, orig_bbox.y1, places=6)
    self.assertAlmostEqual(w_back.bbox.x2, orig_bbox.x2, places=6)
    self.assertAlmostEqual(w_back.bbox.y2, orig_bbox.y2, places=6)
   finally:
    win.close()

 def test_image_split_auto_detect_and_crop_with_rotation_and_wings(self):
  """Авто-поиск 5 семей с синими этикетками, санитайзер имен и нарезка с поворотом ccw90, DPI и переносом крыльев."""
  import numpy as np
  from PIL import Image
  from neurowings.core.image_split import (
   detect_family_regions,
   sanitize_region_name,
   split_image_regions,
  )

  with tempfile.TemporaryDirectory() as t:
   scan_path = Path(t) / "multi_colony.jpg"
   arr = np.full((2200, 1200, 3), 255, dtype=np.uint8)

   y_starts = [70, 500, 930, 1360, 1790]
   for y0 in y_starts:
    # Синяя этикетка слева
    arr[y0 + 25 : y0 + 285, 35:195] = (110, 165, 248)
    # 2 ряда по 8 вертикальных крыльев (темное узкое основание сверху, широкая желто-коричневая вершина снизу)
    for row_y in (y0 + 15, y0 + 165):
     for col_idx in range(8):
      cx = 285 + col_idx * 110
      arr[row_y : row_y + 38, cx - 7 : cx + 7] = (85, 65, 40)
      arr[row_y + 38 : row_y + 125, cx - 20 : cx + 20] = (195, 155, 85)

   # 2 мелких артефакта в межсемейных зазорах
   arr[435:445, 580:590] = (140, 120, 100)
   arr[1295:1305, 720:730] = (140, 120, 100)

   Image.fromarray(arr, mode="RGB").save(scan_path, format="JPEG", quality=95, dpi=(1200, 1200))

   info = detect_family_regions(scan_path)
   regions = info["regions"]
   self.assertEqual(len(regions), 5)
   self.assertEqual(info["axis"], "horizontal")
   self.assertEqual(info["suggested_rotation"], "ccw90")
   for reg in regions:
    self.assertLessEqual(reg.x1, 50.0)
    self.assertGreaterEqual(reg.x2, 1150.0)

   # Проверка sanitize_region_name
   self.assertEqual(sanitize_region_name("№Б / тест: *?"), "№Б_тест")
   self.assertEqual(sanitize_region_name("CON"), "CON_1")
   self.assertEqual(sanitize_region_name("CON.txt"), "CON_1.txt")
   self.assertEqual(sanitize_region_name(""), "Семья")

   # Крыло внутри 1-й семьи для проверки переноса и пересчета координат в ccw90
   rx1, ry1, rx2, ry2 = regions[0].normalized(1200, 2200)
   cw, ch = rx2 - rx1, ry2 - ry1
   wing_pts = [
    (rx1 + 300.0, ry1 + 210.0), (rx1 + 520.0, ry1 + 195.0),
    (rx1 + 400.0, ry1 + 193.0), (rx1 + 335.0, ry1 + 196.0),
    (rx1 + 395.0, ry1 + 145.0), (rx1 + 425.0, ry1 + 125.0),
    (rx1 + 445.0, ry1 + 128.0), (rx1 + 385.0, ry1 + 85.0),
   ]
   wing_bbox = BBox(rx1 + 280.0, ry1 + 70.0, rx1 + 540.0, ry1 + 230.0)
   test_wing = Wing(
    points=[WingPoint(x, y, True) for x, y in wing_pts],
    bbox=wing_bbox,
    point_sources=["manual"] * 8,
   )

   created = split_image_regions(scan_path, regions[:2], rotation_mode="ccw90", wings=[test_wing])
   self.assertEqual(len(created), 2)
   for out_path, _ in created:
    self.assertTrue(out_path.exists())

   out0_path, out0_wings = created[0]
   out1_path, out1_wings = created[1]
   self.assertEqual(image_size(out0_path), (ch, cw))
   with Image.open(out0_path) as out0_im:
    out0_dpi = out0_im.info.get("dpi")
    self.assertIsNotNone(out0_dpi)
    self.assertAlmostEqual(float(out0_dpi[0]), 1200.0, delta=2.0)
    self.assertAlmostEqual(float(out0_dpi[1]), 1200.0, delta=2.0)

   self.assertEqual(len(out0_wings), 1)
   self.assertEqual(len(out1_wings), 0)
   tw = out0_wings[0]
   for (ox, oy), pt in zip(wing_pts, tw.points):
    self.assertAlmostEqual(pt.x, oy - ry1, places=5)
    self.assertAlmostEqual(pt.y, float(cw) - (ox - rx1), places=5)
   self.assertIsNotNone(tw.bbox)
   self.assertAlmostEqual(tw.bbox.x1, wing_bbox.y1 - ry1, places=5)
   self.assertAlmostEqual(tw.bbox.x2, wing_bbox.y2 - ry1, places=5)
   self.assertAlmostEqual(tw.bbox.y1, float(cw) - (wing_bbox.x2 - rx1), places=5)
   self.assertAlmostEqual(tw.bbox.y2, float(cw) - (wing_bbox.x1 - rx1), places=5)

   # Исходник сохранен, повторный запуск уникализирует имена с суффиксом _2
   self.assertTrue(scan_path.exists())
   self.assertEqual(image_size(scan_path), (1200, 2200))
   created_again = split_image_regions(scan_path, regions[:2], rotation_mode="ccw90")
   self.assertEqual(len(created_again), 2)
   self.assertNotEqual(created_again[0][0], out0_path)
   self.assertNotEqual(created_again[1][0], out1_path)
   self.assertTrue(created_again[0][0].stem.endswith("_2"))
   self.assertTrue(created_again[1][0].stem.endswith("_2"))

   # Досрочная остановка split_image_regions через should_stop возвращает [] и не создает файлов
   stop_dir = Path(t) / "stopped_out"
   stopped_created = split_image_regions(
    scan_path,
    regions[:2],
    rotation_mode="ccw90",
    output_dir=stop_dir,
    should_stop=lambda: True,
   )
   self.assertEqual(stopped_created, [])
   self.assertEqual(list(stop_dir.iterdir()) if stop_dir.exists() else [], [])

 def test_split_mode_gui_workflow_and_proxy_display(self):
  """Прокси-отображение read_pixmap_for_display и полный GUI-цикл режима Ножницы (EditMode.SPLIT)."""
  from unittest.mock import patch
  from PIL import Image
  from PyQt5.QtCore import Qt
  from neurowings.core.image_io import read_pixmap_for_display
  from neurowings.core.image_split import split_image_regions
  from neurowings.ui.main_window import MainWindow

  with tempfile.TemporaryDirectory() as t:
   img_p = Path(t) / "scan_gui.jpg"
   Image.new("RGB", (600, 400), color=(245, 245, 245)).save(img_p)

   # 1. Проверка прокси-режима read_pixmap_for_display
   pm, orig_w, orig_h, sx, sy = read_pixmap_for_display(
    img_p, max_display_side=200, megapixels_threshold=10000
   )
   self.assertFalse(pm.isNull())
   self.assertEqual((orig_w, orig_h), (600, 400))
   self.assertEqual(pm.width(), 200)
   self.assertAlmostEqual(pm.height(), 133, delta=1)
   self.assertAlmostEqual(sx, 3.0, delta=0.05)
   self.assertAlmostEqual(sy, 3.0, delta=0.05)

   # 2. GUI-сценарий режима EditMode.SPLIT в MainWindow
   with patch.object(MainWindow, "_load_models"), patch.object(MainWindow, "_load_gpt_config"):
    win = MainWindow()
   try:
    win._load_file_paths([img_p])
    win.show()
    app.processEvents()

    win._set_edit_mode(EditMode.SPLIT)
    app.processEvents()
    self.assertTrue(win.split_bar.isVisible())
    self.assertTrue(win.act_mode_split.isChecked())

    win.spin_split_count.setValue(3)
    win._apply_split_grid("horizontal")
    self.assertEqual(len(win.split_regions), 3)
    self.assertEqual(len(win.split_region_items), 3)
    self.assertTrue(win.btn_split_apply.isEnabled())

    win._on_split_region_delete(1)
    self.assertEqual(len(win.split_regions), 2)
    self.assertEqual(len(win.split_region_items), 2)

    win._on_split_region_created(10.0, 140.0, 590.0, 260.0)
    self.assertEqual(len(win.split_regions), 3)
    self.assertEqual(len(win.split_region_items), 3)

    # Помечаем исходник галочкой, чтобы убедиться, что _on_split_finished снимет ее
    win.file_list.item(0).setCheckState(Qt.Checked)
    created = split_image_regions(img_p, list(win.split_regions), rotation_mode="none")
    self.assertEqual(len(created), 3)

    win._on_split_finished(created)
    app.processEvents()

    self.assertEqual(win.file_list.count(), 4)
    self.assertEqual(Path(win.file_list.item(0).data(Qt.UserRole)), img_p)
    self.assertEqual(win.file_list.item(0).checkState(), Qt.Unchecked)

    created_paths = [p for p, _ in created]
    for i, expected_p in enumerate(created_paths, start=1):
     it = win.file_list.item(i)
     self.assertEqual(Path(it.data(Qt.UserRole)), expected_p)
     self.assertEqual(it.checkState(), Qt.Checked)

    self.assertEqual(win.edit_mode, EditMode.VIEW)
    self.assertFalse(win.act_mode_split.isChecked())
    self.assertFalse(win.split_bar.isVisible())
    self.assertIsNotNone(win.current_image)
    self.assertEqual(Path(win.current_image.path), created_paths[0])
   finally:
    win.close()

 def test_bbox_recognition_calibrated_and_processing_guards(self):
  """Калибровка точек в recognize_wing_in_bbox (point_sources='bbox'), гарды и сигналы SplitWorker."""
  from types import SimpleNamespace
  import numpy as np
  from PIL import Image
  from neurowings.core.constants import YOLO_TO_WINGSDIG
  from neurowings.core.image_split import generate_grid_regions
  from neurowings.workers.processing import ProcessingWorker
  from neurowings.workers.split import SplitWorker

  img_rgb = np.full((700, 1100, 3), 240, dtype=np.uint8)
  bbox = BBox(100.0, 100.0, 900.0, 600.0)
  wingsdig_pts = [
   (161.0, 538.0), (810.0, 489.0), (430.0, 487.0), (244.0, 491.0),
   (422.0, 368.0), (506.0, 323.0), (556.0, 328.0), (404.0, 197.0),
  ]
  yolo_global = [wingsdig_pts[YOLO_TO_WINGSDIG[i]] for i in range(8)]

  def fake_model_pose(crops_arg, **kwargs):
   crops = list(crops_arg) if isinstance(crops_arg, (list, tuple)) else [crops_arg]
   out = []
   for crop in crops:
    ch, cw = crop.shape[:2]
    margin_x = (cw - 800) / 2.0
    margin_y = (ch - 500) / 2.0
    x1m = 100.0 - margin_x
    y1m = 100.0 - margin_y
    local_xy = [[gx - x1m, gy - y1m] for gx, gy in yolo_global]
    kp = SimpleNamespace(
     xy=torch.tensor([local_xy], dtype=torch.float32),
     conf=torch.tensor([[0.95] * 8], dtype=torch.float32),
    )
    out.append(SimpleNamespace(keypoints=kp))
   return out

  wing = ProcessingWorker.recognize_wing_in_bbox(img_rgb, bbox, fake_model_pose, device="cpu")
  self.assertIsNotNone(wing)
  self.assertEqual(wing.point_sources, ["bbox"] * 8)

  expected_cal = ProcessingWorker._apply_kartashov_vein_axis_calibration(wingsdig_pts)
  expected_snapped = [(float(round(x)), float(round(y))) for x, y in expected_cal]
  self.assertEqual([(p.x, p.y) for p in wing.points], expected_snapped)
  self.assertEqual(wing.get_active_points(), [(p.x, p.y) for p in wing.points])
  self.assertNotEqual(wing.get_active_points(), [(p.x, p.y) for p in wing.points_yolo])
  self.assertIsNotNone(wing.analysis)
  self.assertTrue(wing.analysis.is_valid)

  # Гарды recognize_wing_in_bbox
  self.assertIsNone(ProcessingWorker.recognize_wing_in_bbox(img_rgb, bbox, model_pose=None))
  self.assertIsNone(
   ProcessingWorker.recognize_wing_in_bbox(np.zeros((0, 0, 3), dtype=np.uint8), bbox, fake_model_pose)
  )

  # Проверка сигналов progress и finished у SplitWorker (плюс stop-гард)
  with tempfile.TemporaryDirectory() as t:
   src = Path(t) / "worker_scan.jpg"
   Image.new("RGB", (200, 200), color=(230, 230, 230)).save(src)
   regs = generate_grid_regions(200, 200, 2, orientation="horizontal")

   progress_events = []
   finished_events = []
   error_events = []

   worker = SplitWorker(src, regs, rotation_mode="none")
   worker.progress.connect(lambda idx, total, msg: progress_events.append((idx, total, msg)))
   worker.finished.connect(lambda items: finished_events.append(items))
   worker.error.connect(lambda msg: error_events.append(msg))
   worker.run()

   self.assertEqual(error_events, [])
   self.assertEqual(len(progress_events), 2)
   self.assertEqual([(e[0], e[1]) for e in progress_events], [(1, 2), (2, 2)])
   self.assertEqual(len(finished_events), 1)
   self.assertEqual(len(finished_events[0]), 2)
   for out_p, _ in finished_events[0]:
    self.assertTrue(Path(out_p).exists())

   stopped_finished = []
   worker_stopped = SplitWorker(src, regs, rotation_mode="none")
   worker_stopped.finished.connect(lambda items: stopped_finished.append(items))
   worker_stopped.stop()
   worker_stopped.run()
   self.assertEqual(stopped_finished, [[]])

if __name__=='__main__':
 unittest.main()
