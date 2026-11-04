# -*- coding: utf-8 -*-
"""图像读写：imdecode/imencode + fromfile/tofile，兼容中文路径与 16bit 图。"""
import cv2
import numpy as np


def normalize(bgr):
    if bgr.dtype == np.uint16:
        bgr = (bgr.astype(np.float32) / 257.0 + 0.5).astype(np.uint8)
    elif bgr.dtype != np.uint8:
        bgr = np.clip(bgr, 0, 255).astype(np.uint8)
    if bgr.ndim == 2:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
    if bgr.shape[2] == 4:
        bgr = bgr[:, :, :3]
    return bgr


def decode(raw):
    bgr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
    if bgr is None:
        raise RuntimeError("不是可识别的图片文件")
    return normalize(bgr)


def imread(path):
    bgr = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_UNCHANGED)
    if bgr is None:
        raise RuntimeError("读不到图片: " + path)
    return normalize(bgr)


def encode_png(bgr):
    bgr = np.ascontiguousarray(bgr)   # 调色结果是 BGR 反序视图，需连续化
    ok, buf = cv2.imencode(".png", bgr, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    if not ok:
        raise RuntimeError("PNG 编码失败")
    return buf.tobytes()


def encode_jpeg(bgr, quality=88):
    bgr = np.ascontiguousarray(bgr)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise RuntimeError("JPEG 编码失败")
    return buf.tobytes()


def imwrite(path, bgr):
    with open(path, "wb") as f:
        f.write(encode_png(bgr))


def thumbnail(bgr, side=1600):
    h, w = bgr.shape[:2]
    m = max(h, w)
    if m <= side:
        return bgr
    k = side / float(m)
    return cv2.resize(bgr, (max(1, int(w * k)), max(1, int(h * k))),
                      interpolation=cv2.INTER_AREA)
