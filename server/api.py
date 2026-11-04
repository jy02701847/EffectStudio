# -*- coding: utf-8 -*-
"""本地 HTTP API：标准库 http.server，无第三方 Web 框架。

GET  /                  界面
GET  /app.js /style.css 静态资源
GET  /api/health        服务与引擎状态
GET  /api/config        前端可调项
GET  /api/result/<id>   原尺寸 PNG 下载
GET  /api/zip/<batch>   批量结果打包下载
POST /api/process       请求体=原始图片字节，响应=预览 JPEG + X-Meta(参数/耗时)
"""
import base64
import io
import json
import logging
import os
import re
import zipfile
from http.server import BaseHTTPRequestHandler

from core import nr, pipeline

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
_ID = re.compile(r"^[0-9a-f]{12}$")
_BATCH = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")


def _b64e(s):
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _b64d(s):
    return base64.b64decode(s).decode("utf-8", "replace")


class Handler(BaseHTTPRequestHandler):
    server_version = "EffectStudio/1.0"

    @property
    def cfg(self):
        return self.server.cfg

    def log_message(self, fmt, *args):
        logging.getLogger("es").info("%s %s", self.address_string(), fmt % args)

    def _send(self, code, ctype, body, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "X-Meta, X-Result-Id")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass  # 客户端提前关闭（如启动时的单实例探测），不算错误

    def _json(self, obj, code=200):
        self._send(code, "application/json; charset=utf-8",
                   json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _text(self, msg, code=500):
        self._send(code, "text/plain; charset=utf-8", str(msg).encode("utf-8"))

    def do_GET(self):
        path = self.path.split("?")[0]
        try:
            if path == "/api/health":
                self._json({"ok": True, "app": "EffectStudio", "version": "1.0",
                            "nr": nr.status(self.cfg), "strength": self.cfg["strength"]})
                return
            if path == "/api/config":
                self._json({"strength": self.cfg["strength"],
                            "nr": nr.status(self.cfg),
                            "preview_quality": self.cfg.get("preview_quality", 88)})
                return
            if path.startswith("/api/result/"):
                rid = path.rsplit("/", 1)[-1]
                if not _ID.match(rid):
                    self._text("bad id", 400)
                    return
                p = os.path.join(self.cfg["output_dir"], "_results", rid + ".png")
                if not os.path.isfile(p):
                    self._text("结果已不存在，请重新处理", 404)
                    return
                with open(p, "rb") as f:
                    self._send(200, "image/png", f.read(),
                               {"Content-Disposition": 'attachment; filename="%s.png"' % rid})
                return
            if path.startswith("/api/zip/"):
                batch = path.rsplit("/", 1)[-1]
                if not _BATCH.match(batch):
                    self._text("bad batch", 400)
                    return
                folder = os.path.join(self.cfg["output_dir"], batch)
                if not os.path.isdir(folder):
                    self._text("没有这一批的结果", 404)
                    return
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                    for name in sorted(os.listdir(folder)):
                        if name.lower().endswith(".png"):
                            z.write(os.path.join(folder, name), name)
                self._send(200, "application/zip", buf.getvalue(),
                           {"Content-Disposition": 'attachment; filename="%s.zip"' % batch})
                return
            if path == "/favicon.ico":
                self._send(204, "image/x-icon", b"")
                return
            if path in STATIC:
                name, ctype = STATIC[path]
                p = os.path.join(self.cfg["root"], "web", name)
                with open(p, "rb") as f:
                    self._send(200, ctype, f.read())
                return
            self._text("not found", 404)
        except Exception as e:
            logging.getLogger("es").exception("GET %s", path)
            self._text("服务端错误: %r" % (e,), 500)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Opts, X-Name, X-Batch")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_POST(self):
        path = self.path.split("?")[0]
        if path != "/api/process":
            self._text("not found", 404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n <= 0:
                self._text("没有收到图片数据", 400)
                return
            raw = self.rfile.read(n)
            try:
                opts = json.loads(_b64d(self.headers.get("X-Opts", ""))) if self.headers.get("X-Opts") else {}
            except Exception:
                opts = {}
            name = self.headers.get("X-Name", "")
            try:
                filename = _b64d(name) if name else "image.png"
            except Exception:
                filename = "image.png"
            batch = self.headers.get("X-Batch", "") or ""
            if not _BATCH.match(batch):
                batch = ""
            preview, meta = pipeline.process(self.cfg, raw, opts, filename, batch)
            self._send(200, "image/jpeg", preview,
                       {"X-Meta": _b64e(json.dumps(meta, ensure_ascii=False)),
                        "X-Result-Id": meta["id"]})
        except Exception as e:
            logging.getLogger("es").exception("POST /api/process")
            self._text("处理失败: %r" % (e,), 500)
