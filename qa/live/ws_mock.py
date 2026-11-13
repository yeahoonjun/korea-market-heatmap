"""A WebSocket answer for the Python mock Workers (qa/news, qa/extras, qa/world mock_api.py): GET /api/live gets what the real Worker
says outside the session — accepted, {t:'off', reason:'closed', retryAt}, closed 4003 (docs/standards/realtime.md §5-1). The page's
src/live module then keeps polling and remembers retryAt, so the other suites stay console-clean (a 404 handshake would log an error).

    from ws_mock import answer_live   # sys.path += qa/live
    if path == '/api/live': return answer_live(self)
"""
import base64
import hashlib
import json
import struct
import time

GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


def frame(op, payload):
    n = len(payload)
    head = bytes([0x80 | op])
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack('!H', n)
    else:
        head += bytes([127]) + struct.pack('!Q', n)
    return head + payload


def answer_live(handler, reason='closed', retry_in_s=12 * 3600):
    key = handler.headers.get('Sec-WebSocket-Key')
    if not key or (handler.headers.get('Upgrade') or '').lower() != 'websocket':
        body = json.dumps({'error': 'WebSocket 연결만 받아요'}, ensure_ascii=False).encode()
        handler.send_response(426)
        handler.send_header('content-type', 'application/json; charset=utf-8')
        handler.send_header('content-length', str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return
    accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
    handler.wfile.write(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                         f'Sec-WebSocket-Accept: {accept}\r\n\r\n').encode())
    now = int(time.time() * 1000)
    msg = json.dumps({'t': 'off', 'reason': reason, 'retryAt': now + retry_in_s * 1000, 'at': now}).encode()
    handler.wfile.write(frame(0x1, msg) + frame(0x8, struct.pack('!H', 4003) + reason.encode()))
    handler.wfile.flush()
    handler.close_connection = True
