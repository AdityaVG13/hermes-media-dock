"""Fixture server: same-origin media + captions, and CORS, so a boost can be measured.

Run:  python tests/fixtures/serve.py 8771
"""
import functools, http.server, os, sys

class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
    def log_message(self, *a):
        pass

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8771
    root = os.path.dirname(os.path.abspath(__file__))
    handler = functools.partial(H, directory=root)
    http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
