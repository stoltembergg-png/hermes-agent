"""Simple reverse proxy that rewrites the Host header to 127.0.0.1:9119.

Sits between the SSH tunnel and the Hermes dashboard so the dashboard's
Host-header validation accepts the request.
"""

import http.server
import http.client
import urllib.parse

DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 9119
PROXY_PORT = 9120


class HostRewriteProxy(http.server.BaseHTTPRequestHandler):
    def _proxy(self):
        # Build clean headers with rewritten Host
        fwd_headers = {}
        for key, val in self.headers.items():
            if key.lower() == "host":
                fwd_headers["Host"] = f"{DASHBOARD_HOST}:{DASHBOARD_PORT}"
            else:
                fwd_headers[key] = val
        # Force correct Host
        fwd_headers["Host"] = f"{DASHBOARD_HOST}:{DASHBOARD_PORT}"

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else None

        # Forward to dashboard
        conn = http.client.HTTPConnection(DASHBOARD_HOST, DASHBOARD_PORT, timeout=60)
        conn.request(self.command, self.path, body=body, headers=fwd_headers)

        resp = conn.getresponse()

        # Send response back
        self.send_response(resp.status, resp.reason)
        for key, val in resp.getheaders():
            if key.lower() not in ("transfer-encoding", "connection"):
                self.send_header(key, val)
        self.end_headers()

        # Stream response body
        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            self.wfile.write(chunk)

        conn.close()

    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def do_PATCH(self):
        self._proxy()

    def do_HEAD(self):
        self._proxy()

    def do_OPTIONS(self):
        self._proxy()

    def log_message(self, format, *args):
        pass  # silent


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PROXY_PORT), HostRewriteProxy)
    print(f"Proxy on :{PROXY_PORT} -> {DASHBOARD_HOST}:{DASHBOARD_PORT}")
    server.serve_forever()
