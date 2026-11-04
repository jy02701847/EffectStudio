# -*- coding: utf-8 -*-
"""配置加载：config.json（进仓库）+ config.local.json（本机覆盖，不进仓库）。

约定：相对路径一律相对项目根目录；本机专用的绝对路径只写 config.local.json。
环境变量优先级最高，方便在别的机器 / CI 里不改文件直接跑。
"""
import copy
import json
import os
import sys

if getattr(sys, "frozen", False):
    # PyInstaller 打包后：只读资源（web/vendor/config 默认值）在 _MEIPASS，
    # 可写数据（output/tmp/logs/config.local.json）放 exe 旁边，用户能直接找到。
    ROOT = os.path.dirname(sys.executable)
    RES_ROOT = getattr(sys, "_MEIPASS", ROOT)
else:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RES_ROOT = ROOT

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8770,
    "open_browser": True,
    "strength": {
        "contrast": 1.35,
        "shadowhl": 1.35,
        "color": 1.25,
        "clarity": 0.45,
        "radius_div": 300.0,
    },
    "nr": {
        "enabled": "auto",
        "python": "",
        "script": "vendor/nr_pass.py",
        "app": "",
        "timeout": 300,
    },
    "output_dir": "output",
    "tmp_dir": "tmp",
    "log_dir": "logs",
    "preview_quality": 88,
}


def _merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v


def _abs(p, base=None):
    if not p:
        return ""
    return p if os.path.isabs(p) else os.path.join(base or ROOT, p.replace("/", os.sep))


def load():
    cfg = copy.deepcopy(DEFAULTS)
    # 配置文件：exe/项目根优先（用户手改的地方），没有再退回打包资源里的默认值
    for name in ("config.json", "config.local.json"):
        for base in (ROOT, RES_ROOT):
            p = os.path.join(base, name)
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    _merge(cfg, json.load(f))
                break

    env_map = {
        "NR_PYTHON": ("nr", "python"),
        "NR_SCRIPT": ("nr", "script"),
        "NEURALSCREEN_APP": ("nr", "app"),
        "ES_HOST": ("host",),
        "ES_PORT": ("port",),
    }
    for key, path in env_map.items():
        val = os.environ.get(key)
        if not val:
            continue
        if len(path) == 1:
            cfg[path[0]] = int(val) if path[0] == "port" else val
        else:
            cfg[path[0]][path[1]] = val

    cfg["root"] = RES_ROOT
    for k in ("output_dir", "tmp_dir", "log_dir"):
        cfg[k] = _abs(cfg[k])
        os.makedirs(cfg[k], exist_ok=True)
    cfg["nr"]["script"] = _abs(cfg["nr"]["script"], RES_ROOT)
    return cfg
