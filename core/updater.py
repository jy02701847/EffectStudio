# -*- coding: utf-8 -*-
"""在线自动升级。

发布源是一个 latest.json（放 Gitee/GitHub raw、自己的服务器都行）：
    {
      "version": "1.2.0",
      "url":     "https://.../EffectStudio-1.2.0.zip",   # zip 根=文件夹内容(exe/_internal/...)
      "sha256":  "下载包的 sha256（可空，填了就强校验）",
      "notes":   "更新说明（一句话）"
    }

流程：check() 发现新版本 → apply() 后台线程 下载+校验+解压到 _update_new/
→ 写 _do_update.bat → 启动 bat（独立进程）→ 本程序退出
→ bat 等 2 秒 → 结束旧进程 → 覆盖文件 → 重新启动新版 → 删除自身。

Windows 铁律：运行中的 exe 不能覆盖自己，所以"替换文件"这一步必须由
独立进程在主程序退出后完成。
"""
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile

STATUS = {"state": "idle", "msg": ""}   # idle|checking|downloading|ready|restarting|error
_LOCK = threading.Lock()


def _version_tuple(s):
    s = str(s).strip().lstrip("vV")
    parts = []
    for seg in s.split("."):
        num = ""
        for ch in seg:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts) if parts else (0,)


def check(update_url, current_version, timeout=8):
    if not update_url:
        return {"available": False, "reason": "未配置更新源（config.local.json 的 update.url）"}
    try:
        req = urllib.request.Request(update_url, headers={"User-Agent": "EffectStudio"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            info = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"available": False, "reason": "连不上更新源: %s" % e}
    remote = str(info.get("version", "")).strip()
    if not remote:
        return {"available": False, "reason": "更新源格式不对（缺 version）"}
    if _version_tuple(remote) <= _version_tuple(current_version):
        return {"available": False, "reason": "已是最新版本 v%s" % current_version}
    return {"available": True, "version": remote, "url": info.get("url", ""),
            "sha256": str(info.get("sha256", "")), "notes": str(info.get("notes", ""))}


def _download(url, dst, sha256="", timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "EffectStudio"})
    h = hashlib.sha256()
    got = 0
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dst, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            got += len(chunk)
            if total:
                STATUS["msg"] = "下载中 %d/%d MB" % (got >> 20, total >> 20)
    if sha256 and h.hexdigest().lower() != sha256.lower():
        os.remove(dst)
        raise RuntimeError("sha256 校验失败，安装包可能被篡改")


def _extract(zip_path, dest):
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        # 兼容两种 zip：根=文件夹内容 / 根=一层 EffectStudio/ 目录
        top = {n.replace("\\", "/").split("/")[0] for n in names}
        if len(top) == 1 and not any(n.replace("\\", "/").split("/")[0].endswith((".exe", ".json", ".dll")) for n in names[:5]):
            prefix = list(top)[0] + "/"
        else:
            prefix = ""
        for n in names:
            rel = n.replace("\\", "/")[len(prefix):]
            if not rel or rel.endswith("/"):
                continue
            out = os.path.join(dest, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as src, open(out, "wb") as f:
                shutil.copyfileobj(src, f)


def apply(update_url, current_version, app_dir, log=None):
    """整条升级流水线，放进后台线程跑。成功时本进程不会返回（被 bat 接管退出）。"""
    log = log or (lambda m: None)

    def state(s, msg=""):
        STATUS["state"] = s
        STATUS["msg"] = msg
        log("update: %s %s" % (s, msg))

    with _LOCK:
        try:
            state("checking", "正在检查更新…")
            info = check(update_url, current_version)
            if not info.get("available"):
                state("idle", info.get("reason", "已是最新"))
                return
            state("downloading", "开始下载 v%s…" % info["version"])
            pkg = os.path.join(app_dir, "_update_pkg.zip")
            _download(info["url"], pkg, info.get("sha256", ""))
            stage = os.path.join(app_dir, "_update_new")
            if os.path.isdir(stage):
                shutil.rmtree(stage)
            state("downloading", "解压安装包…")
            _extract(pkg, stage)
            os.remove(pkg)

            exe_name = os.path.basename(sys.executable if getattr(sys, "frozen", False)
                                        else "EffectStudio.exe")
            bat = os.path.join(app_dir, "_do_update.bat")
            # 纯 ASCII：cmd 对 bat 里中文的解码不可控
            script = "\r\n".join([
                "@echo off",
                'cd /d "%~dp0"',
                "timeout /t 2 /nobreak >nul",
                'taskkill /im "%s" /f >nul 2>&1' % exe_name,
                "timeout /t 1 /nobreak >nul",
                'robocopy "_update_new" "." /e /move >nul',
                'if exist "_update_new" rmdir /s /q "_update_new"',
                'start "" "%s"' % exe_name,
                '(goto) 2>nul & del /f /q "%~f0"',
                "",
            ])
            with open(bat, "w", encoding="ascii", newline="\r\n") as f:
                f.write(script)
            state("restarting", "已就绪，正在重启升级…")
            DETACHED = 0x00000008 | 0x00000200     # DETACHED_PROCESS | NEW_PROCESS_GROUP
            subprocess.Popen(["cmd", "/c", bat], cwd=app_dir,
                             creationflags=DETACHED, close_fds=True)
            time.sleep(1.0)
            os._exit(0)                            # bat 2 秒后会补刀 taskkill
        except Exception as e:
            logging.getLogger("es").exception("升级失败")
            state("error", "升级失败: %s" % e)
