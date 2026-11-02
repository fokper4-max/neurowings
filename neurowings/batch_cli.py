"""Offline batch recognition and reproducible overlay export."""
import argparse, json, sys, hashlib, os
from pathlib import Path

def main(args):
    parser=argparse.ArgumentParser()
    parser.add_argument('--recognize',required=True)
    parser.add_argument('--output',required=True)
    opts=parser.parse_args(args)
    import torch
    from ultralytics import YOLO
    from PyQt5.QtWidgets import QApplication
    from .core.image_io import read_rgb
    from .core.data_models import ImageData
    from .core.tps_io import save_tps_from_image
    from .workers.processing import ProcessingWorker
    from PIL import Image
    out=Path(opts.output);out.mkdir(parents=True,exist_ok=True)
    photo=Path(opts.recognize)
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
    models=Path(os.environ.get('NEUROWINGS_MODELS_DIR', str(root/'models')))
    manifest=json.loads((Path(__file__).parent/'core/model_manifest.json').read_text())
    for name in ['yolo_detect_best.pt','yolo_pose_best.pt']:
        if hashlib.sha256((models/name).read_bytes()).hexdigest()!=manifest[name]:
            raise ValueError('Model checksum mismatch: '+name)
    torch.set_num_threads(2)
    worker=ProcessingWorker([photo],YOLO(str(models/'yolo_detect_best.pt')),YOLO(str(models/'yolo_pose_best.pt')),None,torch.device('cpu'))
    result={};errors=[]
    worker.finished.connect(result.update);worker.error.connect(errors.append)
    worker.run()
    if errors: raise RuntimeError(errors)
    wings=result[str(photo)]
    wings.sort(key=lambda w:(round(w.get_center()[1]/400),w.get_center()[0]))
    rgb=read_rgb(photo)
    dest=out/(photo.stem+'-normalized.jpg');Image.fromarray(rgb).save(dest,quality=98)
    data=ImageData(dest,wings=wings,width=rgb.shape[1],height=rgb.shape[0])
    save_tps_from_image(data,dest.with_suffix('.tps'))
    rows=[w.get_active_points() for w in wings]
    (out/'points.json').write_text(json.dumps(rows, default=float))
    from PIL import ImageDraw, ImageFont
    overlay=Image.fromarray(rgb)
    draw=ImageDraw.Draw(overlay)
    try:
        point_font=ImageFont.load_default(size=22)
        wing_font=ImageFont.load_default(size=46)
    except TypeError:
        point_font=wing_font=ImageFont.load_default()
    for i,points in enumerate(rows):
        for j,(x,y) in enumerate(points):
            draw.ellipse((x-5,y-5,x+5,y+5),fill='red',outline='white',width=1)
            draw.text((x+8,y-22),str(j+1),fill='blue',font=point_font,stroke_width=1,stroke_fill='white')
        cx=sum(p[0] for p in points)/8;cy=sum(p[1] for p in points)/8
        draw.text((cx,cy-120),'['+str(i+1)+']',fill='blue',font=wing_font,stroke_width=1,stroke_fill='white')
    overlay.save(out/(photo.stem+'-points.jpg'),quality=95)
    print(json.dumps({'wings':len(wings),'points':sum(map(len,rows)),'version':'2.1.0'}),flush=True)
    return 0
