# -*- coding: utf-8 -*-
r"""nr_pass —— 用 NeuralScreen 的离线引擎给一张图过 DLSS5 NR 净化层
由 wash_server 用 D:\NeuralScreen\runtime\python.exe 调用：
  python nr_pass.py <in.png> <out.png>
小图（<=2560x1440）直接整图过网络；大图用"低频差值回贴"：
  NR 在缩到限额内的版本上算出改动量，差值放大回原尺寸叠加到原图。
"""
import sys, os
# NeuralScreen 运行时目录由调用方通过环境变量注入，仓库内不含任何本机绝对路径。
_ns_app = os.environ.get("NEURALSCREEN_APP")
if not _ns_app:
    raise SystemExit("NEURALSCREEN_APP is not set (point it to NeuralScreen/app)")
sys.path.insert(0, _ns_app)
from pathlib import Path
import cv2, numpy as np

PARAMS = dict(style=1, auto_mask=1, intensity=1.00,
              local_tone=0.50, local_structure=1.00, skin_structure=-1.0)


def to8(im):
    if im.dtype == np.uint16:
        return (im.astype(np.float32) / 257.0).clip(0, 255).astype(np.uint8)
    return im


def main():
    src, dst = sys.argv[1], sys.argv[2]
    im = cv2.imdecode(np.fromfile(src, np.uint8), cv2.IMREAD_UNCHANGED)
    if im is None:
        raise SystemExit("cannot read " + src)
    was16 = im.dtype == np.uint16
    if im.shape[2] == 4:
        im = cv2.cvtColor(im, cv2.COLOR_BGRA2BGR)
    im8 = to8(im)
    H, W = im8.shape[:2]
    import media_convert
    _tmpd = os.environ.get("WASH_TMP") or os.path.dirname(os.path.abspath(__file__))
    os.makedirs(_tmpd, exist_ok=True)
    tmp = os.path.join(_tmpd, "_nr_low.png")
    if W <= 2560 and H <= 1440:
        cv2.imencode('.png', im8)[1].tofile(tmp)
        media_convert.convert_image(Path(tmp), Path(dst + ".8.png"), PARAMS)
        nr = cv2.imdecode(np.fromfile(dst + ".8.png", np.uint8), cv2.IMREAD_COLOR)
        try: os.remove(dst + ".8.png")
        except OSError: pass
        out8 = cv2.resize(nr, (W, H)) if nr.shape[:2] != (H, W) else nr
    else:
        sc = min(2560.0 / W, 1440.0 / H)
        lw, lh = max(64, int(W * sc)) // 2 * 2, max(64, int(H * sc)) // 2 * 2
        low = cv2.resize(im8, (lw, lh), interpolation=cv2.INTER_AREA)
        cv2.imencode('.png', low)[1].tofile(tmp)
        media_convert.convert_image(Path(tmp), Path(dst + ".8.png"), PARAMS)
        nr_low = cv2.imdecode(np.fromfile(dst + ".8.png", np.uint8), cv2.IMREAD_COLOR)
        try: os.remove(dst + ".8.png")
        except OSError: pass
        if nr_low.shape[:2] != (lh, lw):
            nr_low = cv2.resize(nr_low, (lw, lh), interpolation=cv2.INTER_AREA)
        delta = nr_low.astype(np.float32) - low.astype(np.float32)
        delta_full = cv2.resize(delta, (W, H), interpolation=cv2.INTER_LANCZOS4)
        out8 = np.clip(im8.astype(np.float32) + delta_full, 0, 255).astype(np.uint8)
    if was16:
        out8 = (out8.astype(np.float32) * 257.0 + 0.5).astype(np.uint16)
    ok, buf = cv2.imencode('.png', out8)
    if not ok:
        raise SystemExit("png encode failed")
    buf.tofile(dst)
    print("nr_pass ok", dst)


main()
