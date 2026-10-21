# -*- coding: utf-8 -*-
"""HTTP JSON 服务（纯标准库，不需要装任何 web 框架）。

    python -m mahjong_kernel.api.server --port 8765

然后把浏览器打开 http://127.0.0.1:8765/ 就是网页界面；
别人也可以直接 POST JSON 调这一套接口。
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from .. import __version__
from ..engine import Engine
from ..protocol import describe

ENGINE = Engine()
ENGINES = {"default": ENGINE}

# 静态文件根目录：项目根下的 webui/
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
WEBUI_DIR = os.path.join(ROOT, "webui")

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


def _engine_for(params):
    return ENGINE


class Handler(BaseHTTPRequestHandler):
    server_version = "MahjongKernel/" + __version__
    protocol_version = "HTTP/1.1"

    # -- 工具 -----------------------------------------------------------

    def _send(self, status, body, content_type="application/json; charset=utf-8",
              extra_headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, indent=None,
                              default=_json_default).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        if os.environ.get("MAHJONG_LOG", "0") == "1":
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- 路由 -----------------------------------------------------------

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path in ("/", "/index.html"):
            return self._serve_static("index.html")

        if path.startswith("/api/"):
            route = path[5:].strip("/")
            try:
                if route == "health":
                    return self._send(200, {"ok": True, "version": __version__,
                                            "service": "mahjong-kernel"})
                if route == "rulesets":
                    return self._send(200, ENGINE.rulesets())
                if route == "protocol":
                    return self._send(200, describe())
                if route == "equations":
                    return self._send(200, {"ok": True,
                                            "equations": describe()["equations"]})
                return self._send(404, {"ok": False, "error": "未知接口: /api/%s" % route})
            except Exception as exc:  # noqa: BLE001
                return self._error(exc)

        # 其余路径当静态文件（限制在 webui 目录内）
        return self._serve_static(path.lstrip("/"))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if not path.startswith("/api/"):
            return self._send(404, {"ok": False, "error": "只支持 /api/* POST"})

        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except ValueError as exc:
                return self._send(400, {"ok": False, "error": "JSON 解析失败: %s" % exc})

            route = path[5:].strip("/")
            engine = _engine_for(payload.get("params") if isinstance(payload, dict) else None)

            if route == "analyze":
                return self._send(200, engine.analyze(payload))
            if route == "score":
                return self._send(200, engine.score(payload))
            if route == "discard":
                return self._send(200, engine.discard(payload))
            if route in ("probability", "prob"):
                return self._send(200, engine.probability(payload))
            if route == "ev":
                return self._send(200, engine.ev(payload))
            if route == "rulesets":
                return self._send(200, engine.register_custom(payload))
            if route == "recognize":
                return self._send(200, recognize_image(payload))
            return self._send(404, {"ok": False, "error": "未知接口: /api/%s" % route})
        except ValueError as exc:
            return self._send(400, {"ok": False, "error": str(exc), "kind": "bad_request"})
        except KeyError as exc:
            return self._send(400, {"ok": False, "error": str(exc), "kind": "bad_ruleset"})
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)

    # -- 静态 -----------------------------------------------------------

    def _serve_static(self, rel):
        safe = posixpath.normpath("/" + rel).lstrip("/")
        if safe.startswith("..") or os.path.isabs(safe):
            return self._send(403, {"ok": False, "error": "越权路径"})
        full = os.path.join(WEBUI_DIR, safe)
        if not os.path.isfile(full):
            if safe in ("index.html", ""):
                return self._send(503, _missing_ui_page(), "text/html; charset=utf-8")
            return self._send(404, {"ok": False, "error": "文件不存在: %s" % safe})
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as fh:
            data = fh.read()
        return self._send(200, data, MIME.get(ext, "application/octet-stream"))

    def _error(self, exc):
        if os.environ.get("MAHJONG_DEBUG") == "1":
            traceback.print_exc()
        return self._send(500, {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)})


def recognize_image(payload):
    """把一张 base64 截图识别成手牌（需要 vision 包：Pillow + numpy）。"""
    import base64
    import io

    raw = payload.get("image") or ""
    if not raw:
        raise ValueError("缺少 image 字段（base64 图片）")
    if "," in raw[:64]:
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("图片 base64 解不开: %s" % exc)

    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    try:
        from vision.image import load_image
        from vision.pack import Layout, TemplatePack, default_layout_path, default_pack_path
        from vision.recognize import recognize, to_request
    except ImportError as exc:
        raise ValueError("截图识别需要 vision 包（Pillow + numpy）: %s" % exc)

    pack_path = payload.get("pack") or default_pack_path()
    layout_path = payload.get("layout") or default_layout_path()
    if not os.path.exists(pack_path):
        raise ValueError(
            "还没有模板包：%s；先跑 python -m vision.cli calibrate 学一遍模板" % pack_path)
    if not os.path.exists(layout_path):
        raise ValueError(
            "还没有版面：%s；先跑 python -m vision.cli calibrate 标一次位置" % layout_path)

    img = load_image(io.BytesIO(blob))
    res = recognize(img, TemplatePack.load(pack_path), Layout.load(layout_path),
                    min_score=float(payload.get("min_score", 0.35)))
    res["request"] = to_request(res, ruleset=payload.get("ruleset", "gb"),
                                turn=int(payload.get("turn", 1)))
    return res


def _json_default(obj):
    try:
        return obj.to_dict()
    except AttributeError:
        return str(obj)


def _missing_ui_page():
    return ("<!doctype html><meta charset='utf-8'>"
            "<title>麻将数学内核</title>"
            "<body style='font-family:system-ui;padding:40px;line-height:1.7'>"
            "<h1>服务已启动，但没找到 webui/index.html</h1>"
            "<p>内核接口可以直接用：<code>POST /api/analyze</code>、"
            "<code>GET /api/protocol</code>。</p>"
            "<p>找回网页界面：确认项目根目录下有 <code>webui/index.html</code>。</p></body>")


def serve(host="127.0.0.1", port=8765, quiet=False):
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = "http://%s:%d/" % (host, port)
    if not quiet:
        print("麻将数学内核 v%s" % __version__)
        print("  网页界面 : %s" % url)
        print("  接口自描述: %sapi/protocol" % url)
        print("  健康检查 : %sapi/health" % url)
        print("  Ctrl+C 停止")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        if not quiet:
            print("\n已停止")
    finally:
        httpd.server_close()
    return httpd


def main(argv=None):
    ap = argparse.ArgumentParser(description="麻将数学内核 HTTP 服务")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    serve(args.host, args.port, args.quiet)


if __name__ == "__main__":
    main()
