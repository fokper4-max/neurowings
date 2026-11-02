"""Canonical EXIF-normalized RGB pixels shared by display and inference."""
import numpy as np
from PIL import Image, ImageOps
from PyQt5.QtGui import QImage, QPixmap

def read_rgb(path):
    with Image.open(str(path)) as image:
        return np.array(ImageOps.exif_transpose(image).convert("RGB"))

def read_pixmap(path):
    rgb = read_rgb(path)
    h, w = rgb.shape[:2]
    return QPixmap.fromImage(QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy())

def image_size(path):
    with Image.open(str(path)) as image:
        w, h = image.size
        return (h, w) if image.getexif().get(274, 1) in (5,6,7,8) else (w,h)
