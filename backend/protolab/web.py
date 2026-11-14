"""Local workbench: python3 -m protolab.web (stdlib only)."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2] / 'frontend'
ASSETS = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}

class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        from .live_eval import public_status, RUN
        if self.path in ('/api/design/results', '/api/design/predictions'):
            try:
                from .design import results, prediction_status
                value = results() if self.path.endswith('results') else prediction_status()
                return self.respond(200, json.dumps(value, allow_nan=False).encode())
            except Exception as exc:
                return self.respond(400, json.dumps({'error': str(exc)}).encode())
        if self.path == '/api/design':
            try:
                from .design import status
                return self.respond(200, json.dumps(status()).encode())
            except Exception as exc:
                return self.respond(502, json.dumps({'error': str(exc)}).encode())
        if self.path == '/api/custom':
            try:
                from .custom_eval import status
                return self.respond(200, json.dumps(status()).encode())
            except Exception as exc:
                return self.respond(502, json.dumps({'error': str(exc)}).encode())
        if self.path == '/api/custom/structure':
            from .custom_eval import RUN as CUSTOM_RUN
            path = CUSTOM_RUN / 'sample_0.pdb'
            return self.respond(200, path.read_bytes(), 'chemical/x-pdb') if path.is_file() else self.respond(404, b'{}')
        if self.path == '/api/live':
            return self.respond(200, json.dumps(public_status()).encode())
        if self.path in ('/api/live/structure/0', '/api/live/structure/1'):
            path = RUN / ('sample_' + self.path[-1] + '.pdb')
            if path.exists():
                return self.respond(200, path.read_bytes(), 'chemical/x-pdb')
            return self.respond(404, b'{"error":"Structure not ready"}')
        if self.path == '/api/live/reference':
            path = RUN / 'reference_pair.pdb'
            if path.exists():
                return self.respond(200, path.read_bytes(), 'chemical/x-pdb')
            return self.respond(404, b'{"error":"Reference not ready"}')
        asset = ASSETS.get(urlparse(self.path).path)
        if not asset:
            return self.respond(404, b'{"error":"Not found"}')
        self.respond(200, (ROOT / asset[0]).read_bytes(), asset[1])

    def do_POST(self):
        if self.path not in ('/api/design/estimate', '/api/design/submit', '/api/design/predictions/estimate', '/api/design/predictions/submit'):
            return self.respond(404, b'{}')
        if self.headers.get('Origin') != 'http://' + self.headers.get('Host', ''):
            return self.respond(403, b'{"error":"Origin rejected"}')
        try:
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size <= 10000: raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(size))
            from .design import estimate, start, estimate_predictions, start_predictions
            actions = {'/api/design/estimate': lambda: estimate(data), '/api/design/submit': lambda: start(data), '/api/design/predictions/estimate': estimate_predictions, '/api/design/predictions/submit': lambda: start_predictions(data)}
            result = actions[self.path]()
            self.respond(200, json.dumps(result).encode())
        except Exception as exc:
            self.respond(400, json.dumps({'error': str(exc)}).encode())


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Protolab: http://127.0.0.1:{args.port} (Ctrl+C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
