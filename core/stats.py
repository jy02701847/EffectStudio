# -*- coding: utf-8 -*-
"""stats.py — 智能Auto 统计引擎（PhotoCraft v35 口径，纯 Python，不依赖宿主）

用法:
  python auto_stats.py <image.png|jpg>            # 打印 JSON 参数
  python auto_stats.py <image> --json out.json    # 写文件

规则口径 = PhotoCraft v35（见 准备档_2026-11-03.md 第二节），逐字对齐。
"""
import sys, os, json, math
import numpy as np
import cv2

PROXY_SIDE = 900


def resp(x, e0, e1):
    """smoothstep 连续响应"""
    t = (x - e0) / (e1 - e0)
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return t * t * (3.0 - 2.0 * t)


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def load_proxy(path):
    im = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_UNCHANGED)
    if im is None:
        raise SystemExit("cannot read " + path)
    h, w = im.shape[:2]
    if im.dtype == np.uint16:
        im = (im.astype(np.float32) / 65535.0 * 255.0)
    else:
        im = im.astype(np.float32)
    if im.ndim == 3 and im.shape[2] == 4:
        im = im[:, :, :3]
    k = max(1, int(math.ceil(max(w, h) / float(PROXY_SIDE))))
    pw, ph = int(math.ceil(w / k)), int(math.ceil(h / k))
    small = cv2.resize(im, (pw, ph), interpolation=cv2.INTER_AREA) if k > 1 else im
    # BGR(A) -> RGB, 0..1 编码域
    rgb = small[:, :, ::-1] / 255.0
    return rgb, (pw, ph), (w, h), k, im[:, :, ::-1] / 255.0


def physical_lap(full_rgb, k, ph):
    """全分辨率物理清晰度：代理块中心行 + 物理上下邻行（3.2 口径）"""
    r, g, b = full_rgb[:, :, 0], full_rgb[:, :, 1], full_rgb[:, :, 2]
    L = 0.2126 * r + 0.7152 * g + 0.0722 * b
    h, w = L.shape
    s1 = s2 = 0.0
    cnt = 0
    for py in range(1, ph - 1):
        yc = py * k + k // 2
        if yc < 1 or yc > h - 2:
            continue
        cur = L[yc]; up = L[yc - 1]; dn = L[yc + 1]
        v = 4.0 * cur[1:-1] - cur[:-2] - cur[2:] - up[1:-1] - dn[1:-1]
        s1 += float(v.sum()); s2 += float((v * v).sum()); cnt += len(v)
    if cnt == 0:
        return 1.0
    m = s1 / cnt
    return float(max(s2 / cnt - m * m, 0.0) ** 0.5)


def compute(path):
    rgb, (pw, ph), (w, h), k, full = load_proxy(path)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    lum = np.clip(0.2126 * r + 0.7152 * g + 0.0722 * b, 0, 1).ravel()
    mx = rgb.max(2); mn = rgb.min(2); sat = (mx - mn).ravel() * 255.0
    n = lum.size
    lum_sorted = np.sort(lum)
    at = lambda f: float(lum_sorted[int(round((len(lum_sorted) - 1) * f))])

    clip_hi = float((lum >= 0.995).sum()) / n
    clip_lo = float((lum <= 0.005).sum()) / n
    sats = np.sort(sat)
    sat_at = lambda f: float(sats[int(round((len(sats) - 1) * f))])
    sat_p50, sat_p90 = sat_at(0.5), sat_at(0.9)
    haze = min(max((at(0.02) * 255.0 - 15.0) / 40.0, 0.0), 1.0)

    # ── 色带（8 带，分母=全像素）──
    nz = sat > 0.06 * 255.0
    dd = np.where(mx.ravel() - mn.ravel() == 0, 1e-6, mx.ravel() - mn.ravel())   # 原始 0..1 差值，勿用 *255 版
    mxc = mx.ravel(); rn = r.ravel(); gn = g.ravel(); bn = b.ravel()
    hue = np.where(np.abs(mxc - rn) < 1e-5,
                   np.mod((gn - bn) / dd * 60.0, 360.0),
                   np.where(np.abs(mxc - gn) < 1e-5,
                            (bn - rn) / dd * 60.0 + 120.0,
                            (rn - gn) / dd * 60.0 + 240.0))
    idx = np.zeros_like(hue, dtype=np.int64)
    idx[(hue < 15) | (hue >= 345)] = 0
    idx[(hue >= 15) & (hue < 45)] = 1
    idx[(hue >= 45) & (hue < 75)] = 2
    idx[(hue >= 75) & (hue < 165)] = 3
    idx[(hue >= 165) & (hue < 195)] = 4
    idx[(hue >= 195) & (hue < 285)] = 5
    idx[(hue >= 285) & (hue < 330)] = 6
    idx[hue >= 330] = 7
    idx = np.where(nz, idx, -1)
    share = [float((idx == j).sum()) / n for j in range(8)]

    # ── 白平衡（高亮未裁剪 5%）──
    thr = at(0.95)
    m = (lum >= thr) & (lum < 0.98)
    nw = int(m.sum())
    cast = tint_read = 0.0
    if nw * 50 >= n:
        cast = float((r.ravel()[m].sum() - b.ravel()[m].sum()) / nw * 255.0)
        tint_read = float((g.ravel()[m].sum() - (r.ravel()[m].sum() + b.ravel()[m].sum()) / 2.0) / nw * 255.0)

    # ── 物理清晰度 ──
    lap = physical_lap(full, k, ph)

    # ── 底层影调 ──
    median = at(0.5)
    exposure = min(max(0.6 * math.log2(0.18 / max(srgb_to_linear(median), 1e-4)), -2.0), 2.0)
    blacks = min(max((0.04 - at(0.001)) * 400.0, -40), 40)
    whites = min(max((0.96 - at(0.999)) * 300.0, -40), 40)
    contrast = min(max((0.6 - (at(0.9) - at(0.1))) * 60.0, 0), 25)

    p = {}
    p['exposure'] = round(exposure, 2)
    p['blacks'] = int(round(blacks))
    p['whites'] = int(round(whites))
    p['contrast'] = int(round(contrast))

    # ── 双向阴影/高光 ──
    p10, p90 = at(0.1), at(0.9)
    sh = (resp(max(0.24 - p10, 0.0), 0.005, 0.12) * 40.0
          - resp(max(p10 - 0.30, 0.0), 0.0, 0.16) * 20.0
          + resp(clip_lo, 0.002, 0.02) * 15.0)
    p['shadows'] = int(round(min(max(sh, -30), 50)))
    hl = (-resp(max(p90 - 0.875, 0.0), 0.0, 0.05) * 45.0
          + resp(max(0.845 - p90, 0.0), 0.005, 0.06) * 20.0
          - resp(clip_hi, 0.0005, 0.008) * 20.0)
    p['highlights'] = int(round(min(max(hl, -50), 40)))

    # ── 色彩 ──
    p['dehaze'] = int(round(min(max(resp(haze, 0.32, 0.85) * 18.0, 0), 18)))
    dry = max(24.0 - sat_p50, 0.0)
    vib = resp(dry, 1.0, 14.0) * 14.0 * (1.0 - 0.5 * resp(sat_p90, 62.0, 88.0))
    p['vibrance'] = int(round(min(max(vib, 0), 14)))
    sat_over = resp(max(sat_p90 - 88.0, 0.0), 1.0, 16.0) * 12.0
    sat_amt = resp(dry, 3.0, 20.0) * 7.0 - sat_over
    p['saturation'] = int(round(min(max(sat_amt, -15), 8)))
    tc = -resp(abs(cast), 2.0, 30.0) * 14.0
    p['temperature'] = int(round(math.copysign(tc, cast))) if abs(cast) > 0.001 else 0
    ti = resp(abs(tint_read), 0.3, 2.6) * 8.0
    p['tint'] = int(round(math.copysign(ti, tint_read))) if abs(tint_read) > 0.001 else 0

    # ── 清晰度 ──
    sh_amt = resp(max(0.075 - lap, 0.0), 0.0, 0.05) * 45.0
    p['sharpen_amount'] = int(round(min(max(sh_amt, 0), 50)))
    tex = resp(max(0.055 - lap, 0.0), 0.0, 0.045) * 15.0
    p['texture'] = int(round(min(max(tex, 0), 15)))
    p['clarity'] = int(round(p['texture'] * 0.7))
    gr = resp(max(0.055 - lap, 0.0), 0.002, 0.035) * 7.0 if p['texture'] > 0.5 else 0
    p['grain'] = int(round(min(max(gr, 0), 8)))

    # ── 色带深化 ──
    o = 10.0 * resp(max(30.0 - sat_p50, 0.0), 1.5, 18.0) * (0.3 + 0.7 * resp(share[1], 0.1, 0.5))
    p['hsl_orange'] = int(round(min(o, 10))) if o >= 2 else 0
    bl = 12.0 * resp(share[5], 0.05, 0.25)
    p['hsl_blue'] = int(round(min(bl, 12))) if bl >= 2 else 0
    p['hsl_green'] = 6 if share[3] > 0.03 else 0

    # ── 平坦度 → 曲线/分色调查 ──
    spread = (at(0.9) - at(0.1)) * 255.0
    flat = max(min(max((55.0 - spread) / 30.0, 0.0), 1.0), min(max((30.0 - sat_p50) / 22.0, 0.0), 1.0))
    p['curve_d'] = int(round(10.0 * resp(flat, 0.15, 0.85))) if flat > 0.15 else 0
    split = 0
    if flat > 0.12:
        sh_mask = (lum >= at(0.1)) & (lum <= at(0.3))
        hi_mask = (lum >= at(0.7)) & (lum < 0.98)
        if sh_mask.sum() * 50 >= n and hi_mask.sum() * 50 >= n:
            rb_s = float((r.ravel()[sh_mask].sum() - b.ravel()[sh_mask].sum()) / sh_mask.sum() * 255.0)
            rb_h = float((r.ravel()[hi_mask].sum() - b.ravel()[hi_mask].sum()) / hi_mask.sum() * 255.0)
            wbspread = abs(rb_s - rb_h)
        else:
            wbspread = 0.0
        present = 1.0 - resp(wbspread, 28.0, 50.0)
        damp = 0.5 if cast > 20.0 else 1.0
        hs = round((4.0 + 6.0 * resp(flat, 0.12, 0.6)) * damp * present)
        if hs >= 2:
            split = int(min(hs, 14))
    p['split_tone'] = split

    # ── 曝光保护 ──
    mean_lum = float(lum.mean())
    if mean_lum > 0.55:
        p['exposure'] = round(max(p['exposure'], -(mean_lum - 0.55) * 0.8), 2)
    else:
        p['exposure'] = round(max(p['exposure'], 0.0), 2)

    # ── 诊断信息（面板显示用）──
    diag = {
        'size': [w, h], 'proxy': [pw, ph], 'k': k,
        'lap_phys': round(lap, 4), 'haze': round(haze, 3),
        'sat_p50': round(sat_p50, 1), 'sat_p90': round(sat_p90, 1),
        'p10': round(p10, 3), 'p90': round(p90, 3),
        'cast': round(cast, 1), 'tint_read': round(tint_read, 2),
        'clip_hi': round(clip_hi, 5), 'clip_lo': round(clip_lo, 5),
        'mean_lum': round(mean_lum, 3), 'flat': round(flat, 3),
        'share_orange': round(share[1], 3), 'share_blue': round(share[5], 3),
    }
    return {'params': p, 'diag': diag}


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: auto_stats.py <image> [--json out.json]")
    res = compute(sys.argv[1])
    if len(sys.argv) > 3 and sys.argv[2] == '--json':
        with open(sys.argv[3], 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


# __main__ 保护：server 需 import 本模块后调用 compute()，
# 直接 import 时不应执行 CLI 的 main()（否则参数不足会 SystemExit）。
if __name__ == "__main__":
    main()