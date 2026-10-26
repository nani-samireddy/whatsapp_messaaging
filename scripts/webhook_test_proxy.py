"""Temporary loopback gateway for a webhook-only development tunnel.

This deliberately forwards neither Desk routes nor browser credentials. Meta's
raw request body and signature reach the app unchanged; the app verifies them.
"""
import argparse
import http.client
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlencode, urlsplit

WEBHOOK_PATH = '/api/method/whatsapp_messaging.messaging.webhooks.receive'
MAX_BODY = 3 * 1024 * 1024
MAX_RESPONSE = 65536
VERIFY_KEYS = {'hub.mode', 'hub.verify_token', 'hub.challenge'}
VERIFY_ALIASES = {key.replace('.', '_'): key for key in VERIFY_KEYS}


def make_handler(site, upstream_port):
    if not re.fullmatch(r'[a-z0-9.-]+\.localhost', site):
        raise ValueError('Use a local development site ending in .localhost')
    if not 1 <= int(upstream_port) <= 65535:
        raise ValueError('Invalid upstream port')

    class WebhookGateway(BaseHTTPRequestHandler):
        server_version = 'WebhookTestGateway'
        sys_version = ''

        def log_message(self, *args):
            # Verification URLs contain a token; payloads can contain contacts.
            pass

        def reply(self, status, body):
            self.send_response(status)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def forward(self):
            self.connection.settimeout(15)
            if len(self.path) > 8192 or any(ord(c) < 32 for c in self.path):
                return self.reply(400, b'Invalid request')
            target = urlsplit(self.path)
            if target.scheme or target.netloc or target.path != WEBHOOK_PATH:
                return self.reply(404, b'Not found')
            if self.command not in ('GET', 'POST'):
                return self.reply(405, b'Only GET and POST are allowed')
            try:
                pairs = parse_qsl(target.query, keep_blank_values=True, max_num_fields=6)
            except ValueError:
                return self.reply(400, b'Invalid query')
            keys = [key for key, _ in pairs]
            if (self.command == 'POST' and target.query) or (
                self.command == 'GET' and (
                    set(keys) - (VERIFY_KEYS | set(VERIFY_ALIASES)) or len(keys) != len(set(keys))
                )
            ):
                return self.reply(400, b'Only webhook verification parameters are allowed')
            verification = {}
            for key, value in pairs:
                canonical = VERIFY_ALIASES.get(key, key)
                if canonical in verification and verification[canonical] != value:
                    return self.reply(400, b'Conflicting webhook verification parameters')
                verification[canonical] = value
            # Meta can send dotted names together with PHP-style underscore
            # aliases. Forward one unambiguous canonical value for each field.
            forward_path = target.path + ('?' + urlencode(verification) if verification else '')
            lengths = self.headers.get_all('Content-Length', [])
            if self.headers.get('Transfer-Encoding') or len(lengths) > 1:
                return self.reply(400, b'Unsupported request framing')
            if not lengths and self.command == 'POST':
                return self.reply(411, b'Content-Length is required')
            raw_length = lengths[0] if lengths else '0'
            if not re.fullmatch(r'[0-9]{1,10}', raw_length):
                return self.reply(400, b'Invalid Content-Length')
            length = int(raw_length)
            if length > MAX_BODY:
                return self.reply(413, b'Payload too large')
            if self.command == 'GET' and length:
                return self.reply(400, b'GET bodies are not supported')
            try:
                body = self.rfile.read(length) if length else b''
            except (OSError, TimeoutError):
                return self.reply(408, b'Request timed out')
            if len(body) != length:
                return self.reply(400, b'Incomplete request body')
            headers = {'Host': site}
            for name in ('Content-Type', 'X-Hub-Signature-256'):
                value = self.headers.get(name)
                if value is not None:
                    headers[name] = value
            conn = http.client.HTTPConnection('127.0.0.1', upstream_port, timeout=15)
            try:
                conn.request(self.command, forward_path, body=body, headers=headers)
                response = conn.getresponse()
                payload = response.read(MAX_RESPONSE + 1)
                if len(payload) > MAX_RESPONSE or 300 <= response.status < 400:
                    return self.reply(502, b'Unexpected webhook response')
                if response.status >= 400:
                    # Do not publish application debug pages or authentication cookies.
                    payload = ('Webhook returned HTTP %s' % response.status).encode()
                return self.reply(response.status, payload)
            except (OSError, http.client.HTTPException):
                return self.reply(502, b'Local webhook is unavailable')
            finally:
                conn.close()

        do_GET = do_POST = do_HEAD = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = forward

    return WebhookGateway


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', default='hms.localhost')
    parser.add_argument('--port', type=int, default=8769)
    parser.add_argument('--upstream-port', type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(args.site, args.upstream_port))
    print('Webhook-only gateway: http://127.0.0.1:%s%s' % (args.port, WEBHOOK_PATH), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
