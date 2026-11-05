"""Lossless companion state, accepted only when its TPS fingerprint matches."""
import hashlib,json,os,tempfile
from dataclasses import asdict
from pathlib import Path
from .data_models import Wing,WingPoint,BBox

def save_project(image, tps):
    path=Path(tps).with_suffix('.nw.json')
    payload={'schema':1,'image':image.path.name,'width':image.width,'height':image.height,
             'tps_sha256':hashlib.sha256(Path(tps).read_bytes()).hexdigest(),
             'wings':[asdict(w) for w in image.wings]}
    data=json.dumps(payload,ensure_ascii=False,allow_nan=False,default=float).encode('utf-8')
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix=path.name,suffix='.tmp')
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def load_project(image,tps):
    path=Path(tps).with_suffix('.nw.json')
    if not path.exists():return False
    if path.stat().st_size>20*1024*1024:raise ValueError('Project file is too large')
    data=json.loads(path.read_text('utf-8'))
    if data.get('schema')!=1 or data.get('image')!=image.path.name or data.get('tps_sha256')!=hashlib.sha256(Path(tps).read_bytes()).hexdigest():return False
    wings=[]
    for value in data['wings']:
        wing=Wing()
        for name in ['points','points_yolo','points_stage1','points_stage2','points_gt']:
            points=value.get(name,[])
            if len(points) not in (0,8):raise ValueError('Invalid project landmark count')
            setattr(wing,name,[WingPoint(**p) for p in points])
        wing.point_sources=value.get('point_sources',['manual']*8)
        wing.is_enabled=bool(value.get('is_enabled', True))
        wing.bbox=BBox(**value['bbox']) if value.get('bbox') else None
        wings.append(wing)
    image.wings=wings;image.width=data['width'];image.height=data['height']
    return True
