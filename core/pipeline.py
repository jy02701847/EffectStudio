# -*- coding: utf-8 -*-
"""处理流水线：原始图片字节 → 统计 → 像素级调色 → 可选 DLSS 净化 → 预览图 + 结果文件。"""
import os
import re
import tempfile
import time
import uuid

from . import enhance, imaging, nr, stats

_SAFE = re.compile(r"[^\w.\-]+")


def _safe(s, limit=60):
    return _SAFE.sub("_", s or "")[:limit] or "image"


def process(cfg, raw, opts=None, filename="image.png", batch=""):
    """返回 (preview_jpeg_bytes, meta)。完整 PNG 落盘，供 /api/result/<id> 下载。"""
    opts = opts or {}
    t0 = time.time()
    bgr = imaging.decode(raw)
    h, w = bgr.shape[:2]
    strength = opts.get("strength") or cfg["strength"]
    want_nr = bool(opts.get("nr"))
    nr_state = nr.status(cfg)
    do_nr = want_nr and nr_state["available"]

    nr_note = ""
    if want_nr and not do_nr:
        nr_note = "跳过（%s）" % nr_state["reason"]

    with tempfile.TemporaryDirectory(dir=cfg["tmp_dir"], prefix="job_") as td:
        src = os.path.join(td, "in.png")
        imaging.imwrite(src, bgr)
        res = stats.compute(src)
        params, diag = res["params"], res["diag"]
        use_auto = bool(opts.get("auto", True))
        out = enhance.apply_auto(bgr, params, diag, strength)[0] if use_auto else bgr
        t_auto = time.time() - t0

        t_nr = 0.0
        if do_nr:
            a = os.path.join(td, "auto.png")
            imaging.imwrite(a, out)
            o = os.path.join(td, "nr.png")
            n0 = time.time()
            try:
                nr_note = nr.run(cfg, a, o, td)
                out = imaging.imread(o)
                t_nr = time.time() - n0
            except Exception as e:
                nr_note = "跳过（%s）" % e
                do_nr = False

        png = imaging.encode_png(out)
        preview = imaging.encode_jpeg(imaging.thumbnail(out, 1600),
                                     cfg.get("preview_quality", 88))

    rid = uuid.uuid4().hex[:12]
    stem = _safe(os.path.splitext(os.path.basename(filename))[0])
    folder = os.path.join(cfg["output_dir"], _safe(batch, 40) if batch else "single")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "%s_%s.png" % (stem, rid[:6])), "wb") as f:
        f.write(png)
    cache = os.path.join(cfg["output_dir"], "_results")
    os.makedirs(cache, exist_ok=True)
    with open(os.path.join(cache, rid + ".png"), "wb") as f:
        f.write(png)

    meta = {
        "id": rid,
        "name": os.path.basename(filename),
        "size": [w, h],
        "auto": bool(opts.get("auto", True)),
        "nr": do_nr,
        "nr_note": nr_note,
        "params": params,
        "diag": {k: diag[k] for k in ("haze", "lap_phys", "flat", "mean_lum")
                 if k in diag},
        "seconds": {"auto": round(t_auto, 2), "nr": round(t_nr, 2),
                    "total": round(time.time() - t0, 2)},
        "png_bytes": len(png),
        "folder": folder,
    }
    return preview, meta
