# -*- coding: utf-8 -*-
"""DLSS5 神经净化适配层：调用外部 NeuralScreen 运行时（子进程）。

仓库内只带适配脚本 vendor/nr_pass.py；NeuralScreen 的 python.exe 与 app 目录
属于用户本机环境，通过 config.local.json 或环境变量指进来，不写死在代码里。
"""
import os
import subprocess
import sys


def _find_app(cfg):
    cands = [
        cfg["nr"].get("app", ""),
        os.environ.get("NEURALSCREEN_APP", ""),
        os.path.join(cfg["root"], "vendor", "NeuralScreen", "app"),
    ]
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "media_convert.py")):
            return c
    return ""


def status(cfg):
    n = cfg["nr"]
    if str(n.get("enabled", "auto")).lower() in ("off", "false", "0", "no"):
        return {"available": False, "reason": "配置里已关闭"}
    py, sc, app = n.get("python", ""), n.get("script", ""), _find_app(cfg)
    if not py or not os.path.isfile(py):
        return {"available": False, "reason": "未配置 NeuralScreen 的 python.exe"}
    if not sc or not os.path.isfile(sc):
        return {"available": False, "reason": "找不到 vendor/nr_pass.py"}
    if not app:
        return {"available": False, "reason": "找不到 NeuralScreen/app（需 media_convert.py）"}
    return {"available": True, "reason": "", "python": py, "script": sc, "app": app}


def run(cfg, src, dst, workdir):
    st = status(cfg)
    if not st["available"]:
        raise RuntimeError("DLSS 不可用: " + st["reason"])
    env = os.environ.copy()
    env["NEURALSCREEN_APP"] = st["app"]
    env["WASH_TMP"] = workdir
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [st["python"], st["script"], src, dst]
    kw = dict(env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
              timeout=int(cfg["nr"].get("timeout", 300)))
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW，避免弹黑窗
    p = subprocess.run(cmd, **kw)
    text = (p.stdout or b"").decode("utf-8", "replace")
    if p.returncode != 0 or not os.path.isfile(dst):
        raise RuntimeError("DLSS 退出码 %s：%s" % (p.returncode, text[-400:]))
    for extra in (dst + ".8.png", os.path.join(workdir, "_nr_low.png")):
        try:
            os.remove(extra)
        except OSError:
            pass
    return text.strip()[-160:]
