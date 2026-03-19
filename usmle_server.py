#!/usr/bin/env python3
"""
USMLE Study Server v2.0
=======================
두 가지 PDF 형식 모두 지원:
  1. ZIP+JPEG (기존 Neurology 파일: PDFsam으로 분할된 것)
  2. 일반 PDF (UWorld QBank 2024: Female Reproductive 등 대용량 파일)

사용법:
  python usmle_server.py                          # 현재 폴더
  python usmle_server.py "C:\\OneDrive\\USMLE"    # 특정 폴더
  python usmle_server.py --port 8765              # 포트 지정

엔드포인트:
  GET /subjects              -> 과목 목록 (폴더 트리)
  GET /info?file=PATH        -> 파일 정보 (페이지 수, 형식)
  GET /page?file=PATH&p=N   -> N번째 페이지 JPEG 반환
  GET /health                -> 서버 상태 확인
"""

import http.server
import json
import os
import sys
import zipfile
import io
import time
import threading
import urllib.request
from urllib.parse import urlparse, parse_qs, unquote

# .env 파일에서 API 키 로드
def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.exists(env_path):
        print(f'  [.env] 파일 없음: {env_path}')
        return
    # utf-8-sig: BOM 자동 제거
    with open(env_path, encoding='utf-8-sig') as f:
        raw = f.read()
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip()
        # 앞뒤 따옴표 제거 ("value" 또는 'value')
        if len(v) >= 2 and v[0] in ('"', "'") and v[-1] == v[0]:
            v = v[1:-1]
        os.environ[k] = v
        # 키 로드 확인 (값은 보안상 일부만 출력)
        if k == 'ANTHROPIC_API_KEY':
            masked = v[:8] + '...' + v[-4:] if len(v) > 12 else '****'
            print(f'  [.env] {k} 로드 완료: {masked}')

load_env()
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# ── 설정 ──────────────────────────────────────────────────────────────────────
PORT = 8765
ROOT_DIR = "."
ROOT_DIRS = []  # 여러 폴더 지원

# pymupdf (일반 PDF 렌더링용)
try:
    import fitz  # PyMuPDF
    PYMUPDF_OK = True
except ImportError:
    PYMUPDF_OK = False

# ── 파일 타입 감지 ─────────────────────────────────────────────────────────────
def detect_file_type(path):
    """
    Returns: 'zip_jpeg' | 'pdf' | 'unknown'
    """
    try:
        with open(path, 'rb') as f:
            header = f.read(4)
        if header[:2] == b'PK':
            return 'zip_jpeg'
        elif header[:4] == b'%PDF':
            return 'pdf'
    except Exception:
        pass
    return 'unknown'


# ── ZIP+JPEG 처리 ─────────────────────────────────────────────────────────────
class ZipJpegFile:
    """기존 PDFsam ZIP+JPEG 형식 처리"""

    def __init__(self, path):
        self.path = path
        self._zf = None
        self._manifest = None
        self._lock = threading.Lock()

    def _open(self):
        if self._zf is None:
            self._zf = zipfile.ZipFile(self.path, 'r')
        return self._zf

    def get_info(self):
        with self._lock:
            zf = self._open()
            if self._manifest is None:
                try:
                    self._manifest = json.loads(zf.read('manifest.json'))
                except Exception:
                    # manifest 없으면 jpeg 개수로 추정
                    jpegs = [n for n in zf.namelist() if n.endswith('.jpeg')]
                    self._manifest = {'num_pages': len(jpegs)}
            return {
                'type': 'zip_jpeg',
                'total_pages': self._manifest['num_pages'],
                'path': self.path,
            }

    def get_page_jpeg(self, page_num):
        """1-indexed page number -> JPEG bytes"""
        with self._lock:
            zf = self._open()
            return zf.read(f'{page_num}.jpeg')


# ── 일반 PDF 처리 ─────────────────────────────────────────────────────────────
class PdfFile:
    """pymupdf로 일반 PDF 렌더링"""

    # 페이지 캐시 (메모리 절약: 최근 20페이지만)
    _cache = {}
    _cache_order = []
    _cache_lock = threading.Lock()
    MAX_CACHE = 20

    def __init__(self, path):
        self.path = path
        self._doc = None
        self._doc_lock = threading.Lock()

    def _open(self):
        if self._doc is None:
            if not PYMUPDF_OK:
                raise RuntimeError(
                    "pymupdf가 설치되어 있지 않습니다.\n"
                    "터미널에서 실행: pip install pymupdf"
                )
            self._doc = fitz.open(self.path)
        return self._doc

    def get_info(self):
        with self._doc_lock:
            doc = self._open()
            return {
                'type': 'pdf',
                'total_pages': len(doc),
                'path': self.path,
            }

    def get_page_jpeg(self, page_num, zoom=1.8, quality=88):
        """
        1-indexed page number -> JPEG bytes
        zoom=1.8: 원본 해상도의 1.8배 (선명도 vs 속도 균형)
        """
        cache_key = f"{self.path}:{page_num}"

        # 캐시 확인
        with PdfFile._cache_lock:
            if cache_key in PdfFile._cache:
                return PdfFile._cache[cache_key]

        # 렌더링
        with self._doc_lock:
            doc = self._open()
            page = doc[page_num - 1]  # 0-indexed
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            jpg_bytes = pix.tobytes('jpeg', jpg_quality=quality)

        # 캐시 저장
        with PdfFile._cache_lock:
            PdfFile._cache[cache_key] = jpg_bytes
            PdfFile._cache_order.append(cache_key)
            # 오래된 캐시 제거
            while len(PdfFile._cache_order) > PdfFile.MAX_CACHE:
                old = PdfFile._cache_order.pop(0)
                PdfFile._cache.pop(old, None)

        return jpg_bytes


# ── 파일 레지스트리 ────────────────────────────────────────────────────────────
_file_registry = {}  # path -> ZipJpegFile | PdfFile

def get_file_handler(path):
    if path not in _file_registry:
        ftype = detect_file_type(path)
        if ftype == 'zip_jpeg':
            _file_registry[path] = ZipJpegFile(path)
        elif ftype == 'pdf':
            _file_registry[path] = PdfFile(path)
        else:
            return None
    return _file_registry[path]


# ── 폴더 스캔 ──────────────────────────────────────────────────────────────────
def scan_subjects(roots):
    """
    여러 폴더를 스캔해서 과목 목록 반환
    roots: str (단일 경로) 또는 list (여러 경로)
    """
    if isinstance(roots, str):
        roots = [roots]

    subjects = []
    seen_paths = set()  # 중복 제거

    for root in roots:
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            continue

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and d != '__pycache__']

            for fname in sorted(filenames):
                if not fname.endswith('.pdf'):
                    continue

                full_path = os.path.join(dirpath, fname)
                full_path = os.path.normpath(full_path)

                # 중복 제거
                if full_path in seen_paths:
                    continue
                seen_paths.add(full_path)

                ftype = detect_file_type(full_path)
                if ftype == 'unknown':
                    continue

                size_mb = os.path.getsize(full_path) / 1024 / 1024

                folder_name = os.path.basename(dirpath)
                file_stem = os.path.splitext(fname)[0]

                if folder_name.lower().replace(' ', '') in file_stem.lower().replace(' ', ''):
                    display_name = folder_name
                else:
                    display_name = file_stem

                # 어느 QBank 인지 표시 (2020 vs 2024)
                group = ''
                for r in roots:
                    if full_path.startswith(os.path.abspath(r)):
                        group = os.path.basename(r)
                        break

                subjects.append({
                    'name': display_name,
                    'file': fname,
                    'abs_path': full_path,
                    'group': group,
                    'type': ftype,
                    'size_mb': round(size_mb, 1),
                })

    # 과목명으로 정렬
    subjects.sort(key=lambda x: x['name'].lower())
    return subjects


# ── HTTP 핸들러 ────────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # 간결한 로그
        path = args[0] if args else ''
        if '/page?' in str(path):
            return  # 페이지 요청은 로그 생략 (너무 많음)
        print(f"  {args[1] if len(args) > 1 else ''} {path[:80]}")

    def send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def do_POST(self):
        self.do_GET()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        try:
            # ── / 또는 /index.html ───────────────────────────────────────
            if path in ('/', '/index.html'):
                index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html')
                if os.path.exists(index_path):
                    with open(index_path, 'rb') as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_cors()
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self._error(404, 'index.html not found')
                return

            # ── /claude  (Claude API 프록시) ──────────────────────────────
            elif path == '/claude':
                if self.command != 'POST':
                    self._error(405, 'POST required')
                    return
                content_len = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_len)

                if not ANTHROPIC_API_KEY:
                    self._error(500, '.env 파일에 ANTHROPIC_API_KEY가 없습니다')
                    return

                req = urllib.request.Request(
                    'https://api.anthropic.com/v1/messages',
                    data=body,
                    headers={
                        'Content-Type': 'application/json',
                        'x-api-key': ANTHROPIC_API_KEY,
                        'anthropic-version': '2023-06-01',
                    },
                    method='POST'
                )
                try:
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        result = resp.read()
                    self.send_response(200)
                    self.send_cors()
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(result)))
                    self.end_headers()
                    self.wfile.write(result)
                except urllib.error.HTTPError as e:
                    err = e.read()
                    self.send_response(e.code)
                    self.send_cors()
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(err)))
                    self.end_headers()
                    self.wfile.write(err)
                return

            # ── /health ──────────────────────────────────────────────────
            elif path == '/health':
                self._json({'status': 'ok', 'pymupdf': PYMUPDF_OK, 'root': ROOT_DIR, 'api_key': bool(ANTHROPIC_API_KEY)})

            # ── /subjects ────────────────────────────────────────────────
            elif path == '/subjects':
                subjects = scan_subjects(ROOT_DIRS)
                self._json({'subjects': subjects, 'roots': ROOT_DIRS})

            # ── /info?file=ABS_PATH ───────────────────────────────────────
            elif path == '/info':
                abs_path = unquote(params.get('file', [''])[0])
                if not abs_path:
                    self._error(400, 'file parameter required')
                    return
                # 슬래시 통일 후 정규화
                abs_path = os.path.normpath(abs_path.replace('/', os.sep).replace('\\', os.sep))
                # 허용된 폴더 안에 있는지 확인
                if not any(abs_path.startswith(os.path.abspath(r)) for r in ROOT_DIRS):
                    self._error(403, 'Access denied')
                    return
                handler = get_file_handler(abs_path)
                if handler is None:
                    self._error(404, f'Cannot read file')
                    return
                info = handler.get_info()
                self._json(info)

            # ── /page?file=ABS_PATH&p=N ───────────────────────────────────
            elif path == '/page':
                abs_path = unquote(params.get('file', [''])[0])
                p_str = params.get('p', ['1'])[0]

                if not abs_path:
                    self._error(400, 'file parameter required')
                    return

                try:
                    page_num = int(p_str)
                except ValueError:
                    self._error(400, f'Invalid page number: {p_str}')
                    return

                abs_path = os.path.normpath(abs_path.replace('/', os.sep).replace('\\', os.sep))
                if not any(abs_path.startswith(os.path.abspath(r)) for r in ROOT_DIRS):
                    self._error(403, 'Access denied')
                    return

                handler = get_file_handler(abs_path)
                if handler is None:
                    self._error(404, f'Cannot read file')
                    return

                t0 = time.time()
                jpg = handler.get_page_jpeg(page_num)
                elapsed = (time.time() - t0) * 1000

                self.send_response(200)
                self.send_cors()
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(jpg)))
                self.send_header('Cache-Control', 'public, max-age=3600')
                self.send_header('X-Render-Ms', f'{elapsed:.0f}')
                self.end_headers()
                self.wfile.write(jpg)

            else:
                self._error(404, f'Unknown endpoint: {path}')

        except Exception as e:
            print(f'  ERROR: {e}')
            import traceback
            traceback.print_exc()
            self._error(500, str(e))

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        self.send_response(200)
        self.send_cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code, msg):
        body = json.dumps({'error': msg}).encode('utf-8')
        self.send_response(code)
        self.send_cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── config.txt 로더 ───────────────────────────────────────────────────────────
def load_config(config_path):
    """config.txt 에서 활성화된 경로 목록을 읽어 반환."""
    dirs = []
    try:
        with open(config_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                dirs.append(line)
        print(f'  config.txt 로드: {len(dirs)}개 경로 활성화')
    except FileNotFoundError:
        print(f'  WARNING: config.txt 없음: {config_path}')
    except Exception as e:
        print(f'  WARNING: config.txt 읽기 실패: {e}')
    return dirs


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    global ROOT_DIR, ROOT_DIRS, PORT

    args = sys.argv[1:]
    dirs = []
    config_path = None

    i = 0
    while i < len(args):
        if args[i] == '--port' and i + 1 < len(args):
            PORT = int(args[i + 1])
            i += 2
        elif args[i] == '--config' and i + 1 < len(args):
            config_path = args[i + 1]
            i += 2
        elif not args[i].startswith('--'):
            dirs.append(args[i])
            i += 1
        else:
            i += 1

    # config.txt 가 있으면 우선 사용
    if config_path:
        dirs = load_config(config_path)

    # 기본값
    if not dirs:
        dirs = ['.']

    ROOT_DIRS = [os.path.abspath(d) for d in dirs]
    ROOT_DIR = ROOT_DIRS[0]  # 하위 호환성

    for d in ROOT_DIRS:
        if not os.path.isdir(d):
            print(f'ERROR: 폴더를 찾을 수 없습니다: {d}')
            sys.exit(1)

    print('=' * 60)
    print('  USMLE Study Server v2.0')
    print('=' * 60)
    for d in ROOT_DIRS:
        print(f'  폴더  : {d}')
    print(f'  주소  : http://localhost:{PORT}')
    print(f'  PyMuPDF: {"✓ 설치됨" if PYMUPDF_OK else "✗ 미설치 (일반 PDF 불가)"}')
    print()

    if not PYMUPDF_OK:
        print('  ⚠  pip install pymupdf')
        print()

    print('  스캔 중...')
    subjects = scan_subjects(ROOT_DIRS)

    if subjects:
        # 그룹별로 출력
        groups = {}
        for s in subjects:
            g = s.get('group', '')
            groups.setdefault(g, []).append(s)

        total = len(subjects)
        print(f'  총 {total}개 파일 발견:')
        for g, items in groups.items():
            print(f'  [{g}] {len(items)}개')
            for s in items[:5]:
                icon = '📦' if s['type'] == 'zip_jpeg' else '📄'
                print(f'    {icon} {s["name"][:45]:<45} {s["size_mb"]:>7.1f}MB')
            if len(items) > 5:
                print(f'    ... 외 {len(items) - 5}개')
    else:
        print('  ⚠  PDF 파일을 찾을 수 없습니다.')

    print()
    print('  서버 실행 중. 브라우저에서 앱을 여세요.')
    print('  종료: Ctrl+C')
    print('=' * 60)

    server = http.server.ThreadingHTTPServer(('localhost', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  서버 종료.')


if __name__ == '__main__':
    main()
