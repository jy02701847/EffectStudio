# -*- coding: utf-8 -*-
"""EffectStudio 入口：双击 start.bat 后运行本文件。

启动本地服务 → 自动打开浏览器。已有一个实例在跑时，只打开浏览器后立即退出。
日志写在 logs/app.log（pythonw 无控制台窗口，靠这个文件排错）。
"""
import json
import logging
import os
import sys
import threading
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer

if getattr(sys, "frozen", False):
    ROOT = os.path.dirname(sys.executable)
else:
    ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import config  # noqa: E402
from server.api import Handler  # noqa: E402


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, cfg):
        self.cfg = cfg
        super().__init__(addr, Handler)


def setup_log(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    p = os.path.join(log_dir, "app.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(p, encoding="utf-8", mode="a")],
    )
    return p


def health(host, port, timeout=0.6):
    url = "http://127.0.0.1:%d/api/health" % port
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == "EffectStudio"
    except Exception:
        return False


def open_later(url, delay=0.6):
    def go():
        threading.Event().wait(delay)
        webbrowser.open(url)
    threading.Thread(target=go, daemon=True).start()


def run_server(cfg):
    """无窗口服务模式（start.bat / 排障用）。"""
    log_path = setup_log(cfg["log_dir"])
    host = cfg["host"]
    port = int(cfg["port"])
    url = "http://127.0.0.1:%d" % port

    if health(host, port):
        logging.info("已有实例在运行，只打开浏览器")
        webbrowser.open(url)
        return

    srv = None
    for p in range(port, port + 12):
        try:
            srv = Server((host, p), cfg)
            port = p
            break
        except OSError:
            continue
    if srv is None:
        logging.error("端口 %d~%d 都被占用，启动失败", port, port + 11)
        return

    url = "http://127.0.0.1:%d" % port
    with open(os.path.join(cfg["log_dir"], "last_url.txt"), "w", encoding="utf-8") as f:
        f.write(url)
    logging.info("EffectStudio 启动: %s  日志: %s", url, log_path)
    if cfg.get("open_browser", True):
        open_later(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def start_server_thread(cfg):
    """起 HTTP 服务线程，返回 url；被窗口模式复用。"""
    port = int(cfg["port"])
    srv = None
    for p in range(port, port + 12):
        try:
            srv = Server(("127.0.0.1", p), cfg)
            port = p
            break
        except OSError:
            continue
    if srv is None:
        raise RuntimeError("端口 %d~%d 都被占用" % (port, port + 11))
    url = "http://127.0.0.1:%d" % port
    with open(os.path.join(cfg["log_dir"], "last_url.txt"), "w", encoding="utf-8") as f:
        f.write(url)
    logging.info("EffectStudio 启动: %s", url)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return url


def run_gui(cfg):
    """原生窗口模式：pywebview 壳 + 本地 HTTP API，观感与正经桌面软件一致。"""
    setup_log(cfg["log_dir"])
    if health(cfg["host"], int(cfg["port"])):
        logging.info("已有实例，直接开窗口连它")
    url = start_server_thread(cfg)
    import webview  # 延迟导入：--server 模式不需要它
    webview.create_window(
        "EffectStudio 效果图优化",
        url,
        width=1180, height=840, min_size=(920, 660),
        background_color="#101418",
    )
    webview.start()


def main():
    cfg = config.load()
    server_mode = "--server" in sys.argv or not cfg.get("gui", True)
    if server_mode:
        run_server(cfg)
    else:
        run_gui(cfg)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.getLogger("es").exception("启动失败")
        raise
