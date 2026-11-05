"""Validated TPS import and atomic WingsDig-compatible export."""
from pathlib import Path
import math, os, tempfile
from .data_models import Wing, WingPoint
from .image_io import image_size

def load_tps_into_image(img_data, tps_path):
    path = Path(tps_path)
    if not path.exists(): return
    width, height = (img_data.width, img_data.height) if img_data.height else image_size(img_data.path)
    raw = path.read_bytes()
    try: text = raw.decode('utf-8-sig')
    except UnicodeDecodeError: text = raw.decode('cp1251')
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    wings=[]; i=0
    while i < len(lines):
        if not lines[i].upper().startswith('LM='):
            i+=1; continue
        count=int(lines[i].split('=',1)[1]); i+=1
        if count < 0 or count % 8 or count > 100000: raise ValueError('TPS: LM должен быть неотрицательным кратным 8')
        points=[]
        for _ in range(count):
            if i >= len(lines): raise ValueError('TPS: недостаточно координат')
            fields=lines[i].replace(',','.').split(); i+=1
            if len(fields)!=2: raise ValueError('TPS: повреждённая строка координат')
            x,y=map(float,fields)
            if not math.isfinite(x) or not math.isfinite(y): raise ValueError('TPS: недопустимые координаты')
            points.append(WingPoint(x,height-y))
        while i<len(lines) and not lines[i].upper().startswith('LM='):
            i+=1
        wings.extend(
            Wing(
                points=[WingPoint(p.x, p.y) for p in points[j:j+8]],
                points_gt=[WingPoint(p.x, p.y) for p in points[j:j+8]],
                point_sources=['gt'] * 8,
            )
            for j in range(0, count, 8)
        )
    img_data.width=width; img_data.height=height; img_data.wings=wings

def save_tps_from_image(img_data, tps_path):
    path=Path(tps_path)
    lines=[f'LM={len(img_data.wings)*8}']
    for wing in img_data.wings:
        points=wing.get_active_points()
        if len(points)!=8: raise ValueError('TPS: требуется 8 точек на крыло')
        for x,y in points:
            if not math.isfinite(x) or not math.isfinite(y): raise ValueError('TPS: недопустимые координаты')
            lines.append(f'{x:.5f} {img_data.height-y:.5f}'.replace('.',','))
    lines.extend([f'IMAGE={img_data.path.name}','ID=1'])
    text='\r\n'.join(lines)+'\r\n'
    try: payload=text.encode('cp1251')
    except UnicodeEncodeError: payload=text.encode('utf-8')
    fd,temp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as handle: handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)
