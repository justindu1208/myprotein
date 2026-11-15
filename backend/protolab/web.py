"""Local workbench: python3 -m protolab.web (stdlib only)."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2] / 'frontend'
ASSETS = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
ASSETS['/molecular-evidence.js'] = ('molecular-evidence.js', 'text/javascript')
ASSETS['/molecular-evidence.css'] = ('molecular-evidence.css', 'text/css')

class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type + ('; charset=utf-8' if content_type.startswith('text/') or content_type=='application/json' else ''))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def respond_file(self, path, mime):
        import re
        size=path.stat().st_size
        start,end,status=0,size-1,200
        requested=self.headers.get('Range')
        if requested:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
            if not match or not any(match.groups()):
                self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
            a,b=match.groups()
            if a:start=int(a);end=min(int(b),size-1) if b else size-1
            else:start=max(0,size-int(b))
            if start>=size or start>end:
                self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
            status=206
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(end-start+1))
        self.send_header('Accept-Ranges','bytes')
        self.send_header('X-Content-Type-Options','nosniff')
        if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        with path.open('rb') as stream:
            stream.seek(start);remaining=end-start+1
            while remaining:
                chunk=stream.read(min(65536,remaining))
                if not chunk:break
                try:self.wfile.write(chunk)
                except (BrokenPipeError,ConnectionResetError):break
                remaining-=len(chunk)

    def do_GET(self):
        if urlparse(self.path).path.startswith('/api/experiments/'):
            try:
                from . import experiment
                return self.respond(200,json.dumps(experiment.status(urlparse(self.path).path.split('/')[-1]),allow_nan=False).encode())
            except Exception as exc:return self.respond(400,json.dumps({'error':str(exc)}).encode())
        if urlparse(self.path).path=='/api/research/tasks':
            from .research import list_tasks
            return self.respond(200,json.dumps(list_tasks(),allow_nan=False).encode())
        if urlparse(self.path).path=='/api/research/demos':
            from .research import demos
            return self.respond(200,json.dumps(demos(),allow_nan=False).encode())
        if urlparse(self.path).path.startswith('/api/research/'):
            try:
                from .research import status
                return self.respond(200,json.dumps(status(urlparse(self.path).path.split('/')[-1]),allow_nan=False).encode())
            except Exception as exc:return self.respond(400,json.dumps({'error':str(exc)}).encode())
        if urlparse(self.path).path.startswith('/api/visualizations'):
            try:
                from urllib.parse import parse_qs
                from . import visualizations as viz
                from . import visualization_store as store
                parsed=urlparse(self.path);parts=parsed.path.strip('/').split('/');query=parse_qs(parsed.query)
                if parts==['api','visualizations']:
                    result={'runs':store.catalog(),'renderer':viz.renderer.check()}
                elif len(parts)==4 and parts[-1]=='manifest': result=viz.public_manifest(parts[2])
                elif len(parts)==5 and parts[-1]=='status': result=viz.renderer.get_status(parts[2],parts[3],query.get('preset',['cartoon'])[0])
                elif len(parts)==5:
                    path,mime=viz.serve_asset(parts[2],parts[3],parts[4]);return self.respond_file(path,mime)
                elif len(parts)==7 and parts[4]=='renders':
                    path,mime=viz.serve_asset(parts[2],parts[3],parts[6],parts[5]);return self.respond_file(path,mime)
                else:return self.respond(404,b'{"error":"Unknown visualization endpoint"}')
                return self.respond(200,json.dumps(result,allow_nan=False).encode())
            except Exception as exc:
                return self.respond(400,json.dumps({'error':str(exc)}).encode())
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
        if self.path in ('/api/experiments/start','/api/experiments/retry'):
            if self.headers.get('Origin') != 'http://' + self.headers.get('Host',''):return self.respond(403,b'{"error":"Origin rejected"}')
            try:
                from . import experiment
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=5000:raise ValueError('Invalid request size')
                data=json.loads(self.rfile.read(size))
                result=experiment.start(data.get('id'),data.get('candidate_ids')) if self.path.endswith('/start') else experiment.retry_rejected(data.get('id'))
                return self.respond(200,json.dumps(result,allow_nan=False).encode())
            except Exception as exc:return self.respond(400,json.dumps({'error':str(exc)}).encode())
        if self.path.startswith('/api/research/'):
            if self.headers.get('Origin') != 'http://' + self.headers.get('Host',''):
                return self.respond(403,b'{"error":"Origin rejected"}')
            try:
                from . import research
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=5000:raise ValueError('Invalid request size')
                data=json.loads(self.rfile.read(size))
                if self.path=='/api/research/create':result=research.create(data)
                elif self.path=='/api/research/resolve':result=research.resolve(data)
                elif self.path=='/api/research/start':result=research.start(data.get('id'))
                else:raise ValueError('Unknown research action')
                return self.respond(200,json.dumps(result,allow_nan=False).encode())
            except Exception as exc:return self.respond(400,json.dumps({'error':str(exc)}).encode())
        if self.path.startswith('/api/visualizations/'):
            if self.headers.get('Origin') != 'http://' + self.headers.get('Host',''):
                return self.respond(403,b'{"error":"Origin rejected"}')
            try:
                from . import visualizations as viz
                size=int(self.headers.get('Content-Length',0))
                if not 0<size<=4000:raise ValueError('Invalid request size')
                data=json.loads(self.rfile.read(size));parts=self.path.strip('/').split('/')
                if self.path=='/api/visualizations/resolve':result=viz.resolve_target(data.get('accession'),data.get('species'))
                elif len(parts)==5 and parts[-1]=='render':result=viz.renderer.submit(parts[2],parts[3],data.get('preset','cartoon'))
                elif self.path=='/api/visualizations/check':result=viz.renderer.check(refresh=True)
                else:return self.respond(404,b'{"error":"Unknown visualization action"}')
                return self.respond(200,json.dumps(result,allow_nan=False).encode())
            except Exception as exc:return self.respond(400,json.dumps({'error':str(exc)}).encode())
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
    from .research import resume_pending, install_bundled_demos
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    install_bundled_demos()
    resume_pending()
    from .experiment import resume_pending as resume_experiments
    resume_experiments()
    print(f'Protolab: http://127.0.0.1:{args.port} (Ctrl+C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
