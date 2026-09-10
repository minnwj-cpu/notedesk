# -*- coding: utf-8 -*-
"""로컬 미리보기 — docs 폴더를 http://localhost:8765 로 띄운다 (배포 전 확인용)"""
import http.server, os, sys
from pathlib import Path
os.chdir(Path(__file__).resolve().parent / "docs")
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
class H(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".webmanifest": "application/manifest+json", ".js": "text/javascript"}
    def end_headers(self):
        self.send_header("Cache-Control", "no-store"); super().end_headers()
    def log_message(self, f, *a): sys.stderr.write("%s %s\n" % (self.address_string(), f % a))
print("serving", os.getcwd(), "on", port, flush=True)
http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
