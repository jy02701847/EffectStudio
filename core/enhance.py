# -*- coding: utf-8 -*-
"""enhance.py — 像素级调色（Lab 亮度域，不引入色偏）。

设计要点（为什么用 Lab）：
  曲线 / 色阶 / 对比 / 质感 / 锐化 **只作用于 L（亮度）**，a/b（色度）不受影响。
  旧版在 RGB 上逐通道做同样运算，暗部压暗时通道差值被放大 2 倍以上，
  白墙、木饰面会明显发红发黄 —— 这是之前"偏色"的根因。
  饱和度用 a/b 等比缩放（比 HSV 稳，不会带出色相偏移），
  色温/色调直接加在 b/a 上（物理含义明确）。

可作为模块 import，也可命令行自测：
  python -m core.enhance process <in> <out>
"""
import json
import os
import sys
import time

import cv2
import numpy as np

from . import stats

compute = stats.compute


def imread(path):
    bgr = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_UNCHANGED)
    if bgr is None:
        raise RuntimeError("cannot read: " + path)
    if bgr.dtype == np.uint16:
        bgr = (bgr / 257.0).astype(np.uint8)
    if bgr.ndim == 2:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
    if bgr.shape[2] == 4:
        bgr = bgr[:, :, :3]
    return bgr


def imwrite(path, bgr):
    ok, buf = cv2.imencode(".png", bgr, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    if not ok:
        raise RuntimeError("encode failed")
    buf.tofile(path)


def s2l(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def l2s(x):
    return np.where(x <= 0.0031308, x * 12.92,
                    1.055 * np.power(np.clip(x, 0, None), 1.0 / 2.4) - 0.055)


def softstep(e0, e1, x):
    """平滑权重 0→1（smoothstep），用于高光区权重过渡，避免出现硬边断层"""
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3.0 - 2.0 * t)


def softlight(a, b):
    """PS 柔光混合, a=base b=blend, 均 0..1"""
    d = np.where(a <= 0.25, ((16 * a - 12) * a + 4) * a,
                 np.sqrt(np.clip(a, 0, None)))
    lo = a - (1.0 - 2.0 * b) * a * (1.0 - a)
    hi = a + (2.0 * b - 1.0) * (d - a)
    return np.where(b <= 0.5, lo, hi)


def quantiles_lum(L, fs=(0.001, 0.999)):
    """在亮度通道上取分位数；先降采样，8K 也只要几毫秒。"""
    h, w = L.shape
    k = max(1, int(np.ceil(max(h, w) / 900.0)))
    small = cv2.resize(L, (max(1, w // k), max(1, h // k)),
                       interpolation=cv2.INTER_AREA)
    return [float(np.quantile(small, f)) for f in fs]


def apply_auto(bgr, params, diag, strength=None):
    # 强度按调用方逐次传入（局部变量），并发请求之间不会串值
    K_CONTRAST = 1.35
    K_SHADOWHL = 1.35
    K_COLOR = 1.25
    CLARITY_AMOUNT = 0.45
    CLARITY_RADIUS_DIV = 300.0
    WB = 0.0
    if strength:
        K_CONTRAST = float(strength.get("contrast", K_CONTRAST))
        K_SHADOWHL = float(strength.get("shadowhl", K_SHADOWHL))
        K_COLOR = float(strength.get("color", K_COLOR))
        CLARITY_AMOUNT = float(strength.get("clarity", CLARITY_AMOUNT))
        CLARITY_RADIUS_DIV = float(strength.get("radius_div", CLARITY_RADIUS_DIV))
        WB = float(strength.get("wb", 0.0))          # 手调色温：负=冷，正=暖，±100

    p = params
    x = bgr[:, :, ::-1].astype(np.float32) / 255.0      # RGB 编码域
    h, w = x.shape[:2]
    t0 = time.time()
    marks = []

    def mark(name):
        marks.append("%s=%.2fs" % (name, time.time() - t0))

    # 1 曝光：线性光里三通道同乘一个系数，色比不变 → 不偏色
    expo = float(p["exposure"])
    if abs(expo) > 1e-4:
        x = np.clip(l2s(s2l(x) * (2.0 ** expo)), 0, 1)
    mark("exposure")

    # 2 转 Lab：L=亮度，a/b=色度。之后亮调操作只碰 L
    lab = cv2.cvtColor(x, cv2.COLOR_RGB2Lab)
    L = np.clip(lab[:, :, 0] / 100.0, 0, 1)
    src_p50 = quantiles_lum(L, fs=(0.5,))[0]      # 原图中位亮度，作为"不洗亮"的锚点

    # 3 曲线：暗部提亮 / 高光回收（只动亮度）
    lift = float(np.clip(p["shadows"] * 1.15 * K_SHADOWHL, -16, 55))
    top_adj = float(np.clip(p["highlights"] * 0.9 * K_SHADOWHL, -35, 28))
    px = np.array([0.0, 64.0, 128.0, 192.0, 255.0]) / 255.0
    py = np.array([np.clip(lift, 0, 255),
                   64 + lift * 0.68,
                   128 + lift * 0.15,
                   192 + top_adj * 0.85,
                   255.0]) / 255.0
    L = np.interp(L, px, py).astype(np.float32)
    mark("curve")

    # 4 色阶：黑白场（只动亮度，这是去灰最有效的一步）
    #   白场必须温和：效果图本来就没有纯白，把 99.9 分位硬拉到 255 会直接把白墙推爆
    #   （场景 10_1 实测就是这么把 p90 从 222 顶到 243 的）。系数 0.55 且最多拉 4 级。
    p001, p999 = quantiles_lum(L)
    in_black = float(np.clip((p001 * 255 - 2) * 0.8 * K_CONTRAST, 0, 60)) / 255.0
    in_white = float(np.clip(255 - (255 - p999 * 255) * 0.60 * K_CONTRAST, 195, 252)) / 255.0
    in_white = max(in_white, p999 - 4.0 / 255.0)
    L = np.clip((L - in_black) / max(in_white - in_black, 0.2), 0, 1)
    mark("levels")

    # 5 对比（只动亮度，不会把色差放大成染色）
    #   高光阻尼：0.62 以下全额，越接近 1.0 力度越小。
    #   线性对比端点不固定，会把白墙/天花直接推到 255 变死白 —— 这是"还有点曝光"的根因。
    haze = float(diag.get("haze", 0.45))
    # 对比总和设上限 0.22：contrast 与 dehaze 都会推高对比，叠起来（场景 10_1 = 15+18）
    # 足以把中高调顶到饱和，所以必须封顶。
    c = min((p["contrast"] + 15.0 * haze) / 100.0, 0.22) * K_CONTRAST
    damp = ((1.0 - 0.78 * softstep(0.62, 0.98, L))
            * (0.45 + 0.55 * softstep(0.02, 0.32, L)))   # 两端都收：高光不爆、暗部不压成死黑
    L = np.clip(L + (L - 0.5) * c * damp, 0, 1)
    mark("contrast")

    # 6 饱和度：Lab 的 a/b 等比缩放，色相不会跑
    sat = p["saturation"] / 100.0 * K_COLOR
    vib = p["vibrance"] / 100.0 * K_COLOR
    scale = float(np.clip(1.0 + sat + vib * 0.5, 0.55, 1.40))
    if abs(scale - 1.0) > 1e-3:
        lab[:, :, 1] *= scale
        lab[:, :, 2] *= scale
    mark("vibrance")

    # 7 色温 / 色调 / 手调（Lab：a+ 偏红品红，b+ 偏黄）
    t = float(p["temperature"]) / 100.0 * K_COLOR
    ti = float(p.get("tint", 0)) / 100.0 * K_COLOR
    a_shift = t * 3.5 + ti * 8.0 + (WB / 100.0) * 6.0
    b_shift = t * 10.0 + (WB / 100.0) * 12.0
    if abs(a_shift) > 1e-3 or abs(b_shift) > 1e-3:
        lab[:, :, 1] += a_shift
        lab[:, :, 2] += b_shift
    mark("temperature")

    # 8 质感：高反差保留 + 柔光（只作用在亮度上）
    radius = max(3, int(round(min(h, w) / CLARITY_RADIUS_DIV)))
    if CLARITY_AMOUNT > 1e-3:
        blur = cv2.GaussianBlur(L, (0, 0), float(radius))
        hp = L - blur + 0.5
        L = np.clip(L * (1.0 - CLARITY_AMOUNT) + softlight(L, hp) * CLARITY_AMOUNT, 0, 1)
    mark("clarity")

    # 9 锐化：只锐化亮度，避免彩色边缘
    amt = float(p["sharpen_amount"]) / 100.0
    if amt > 0:
        L = np.clip(L + amt * (L - cv2.GaussianBlur(L, (0, 0), 1.0)), 0, 1)
    mark("sharpen")

    # 10 中调锚定：洗图的原则是"不变亮"。前面几步（色阶/对比/柔光）会把中调整体抬上去，
    #    这里用 gamma 把中位亮度贴回原图；只在 0.35 以上渐入，深暗部不动。
    out_p50 = quantiles_lum(L, fs=(0.5,))[0]
    gamma_used = 1.0
    if src_p50 > 0.05 and out_p50 > src_p50 * 1.015:
        gamma_used = float(np.clip(np.log(src_p50) / np.log(max(out_p50, 1e-3)), 1.0, 1.6))
        w_mid = softstep(0.34, 0.56, L)
        L = np.clip(L + (np.power(L, gamma_used) - L) * w_mid, 0, 1)
    mark("anchor")

    # 11 高光收口：0.78 以上做 C1 连续的二阶压缩，最亮压到 0.97。
    #    必须是"压缩"而不是"截断"——截断会在大片高光上堆出一条 0.97 的白平台，
    #    看起来跟过曝一样（之前 6% 像素 ≥250 就是这个毛病）。
    HI_KNEE, HI_TOP = 0.78, 0.970
    if float(L.max()) > HI_KNEE:
        span = 1.0 - HI_KNEE
        curv = 1.0 - (HI_TOP - HI_KNEE) / span          # 二次项系数，保证 L=1 → HI_TOP
        t = np.clip((L - HI_KNEE) / span, 0.0, 1.0)
        y = HI_KNEE + span * (t - curv * t * t)          # knee 处斜率仍为 1，无接缝
        L = np.where(L > HI_KNEE, y, L)
    mark("highlight")

    lab[:, :, 0] = L * 100.0
    np.clip(lab[:, :, 1], -120, 120, out=lab[:, :, 1])
    np.clip(lab[:, :, 2], -120, 120, out=lab[:, :, 2])
    x = np.clip(cv2.cvtColor(lab, cv2.COLOR_Lab2RGB), 0, 1)

    out = (x * 255.0 + 0.5).astype(np.uint8)[:, :, ::-1]
    return out, marks, {"radius": radius, "p001": round(p001, 4),
                        "p999": round(p999, 4),
                        "in_black": round(in_black * 255, 1),
                        "in_white": round(in_white * 255, 1),
                        "src_p50": round(src_p50, 4), "out_p50": round(out_p50, 4),
                        "gamma": round(gamma_used, 3),
                        "a_shift": round(a_shift, 2), "b_shift": round(b_shift, 2)}


def process(src, dst):
    t0 = time.time()
    bgr = imread(src)
    res = compute(src)
    out, marks, extra = apply_auto(bgr, res["params"], res["diag"])
    imwrite(dst, out)
    print("INPUT :", src, bgr.shape[1], "x", bgr.shape[0])
    print("OUTPUT:", dst, os.path.getsize(dst), "B")
    print("PARAMS:", json.dumps(res["params"], ensure_ascii=False))
    print("EXTRA :", json.dumps(extra, ensure_ascii=False))
    print("STEPS :", " ".join(marks))
    print("TOTAL : %.2fs" % (time.time() - t0))


def compare(paths, dst):
    imgs = []
    labels = ["BEFORE", "SmartAuto", "SmartAuto + DLSS NR"]
    for p in paths:
        im = imread(p)
        tw = 640
        th = int(round(im.shape[0] * tw / im.shape[1]))
        im = cv2.resize(im, (tw, th), interpolation=cv2.INTER_AREA)
        imgs.append(im)
    h = min(i.shape[0] for i in imgs)
    imgs = [i[:h] for i in imgs]
    panel = np.hstack(imgs)
    for i, im in enumerate(imgs):
        x0 = sum(j.shape[1] for j in imgs[:i]) + 12
        cv2.putText(panel, labels[i], (x0, 34), cv2.FONT_HERSHEY_SIMPLEX,
                    0.85, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(panel, labels[i], (x0, 34), cv2.FONT_HERSHEY_SIMPLEX,
                    0.85, (255, 255, 255), 2, cv2.LINE_AA)
    imwrite(dst, panel)
    print("COMPARE:", dst, panel.shape[1], "x", panel.shape[0],
          os.path.getsize(dst), "B")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: enhance.py process|compare ...")
    cmd = sys.argv[1]
    if cmd == "process":
        process(sys.argv[2], sys.argv[3])
    elif cmd == "compare":
        compare(sys.argv[2:-1], sys.argv[-1])
    else:
        raise SystemExit("unknown command: " + cmd)
