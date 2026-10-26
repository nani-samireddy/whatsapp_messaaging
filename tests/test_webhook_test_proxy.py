"""Exercise the public boundary using only temporary loopback HTTP servers."""
import hashlib
import hmac
import http.client
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

from scripts.webhook_test_proxy import MAX_BODY, WEBHOOK_PATH, make_handler


class TestWebhookGateway(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self):
                data = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                cls.requests.append((self.command, self.path, dict(self.headers), data))
                self.send_response(cls.status)
                self.send_header('Set-Cookie', 'sid=must-not-be-forwarded')
                self.send_header('Content-Length', str(len(cls.payload)))
                self.end_headers()
                self.wfile.write(cls.payload)

            do_GET = do_POST = respond

        cls.upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        cls.gateway = ThreadingHTTPServer(('127.0.0.1', 0), make_handler('hms.localhost', cls.upstream.server_port))
        cls.threads = []
        for server in (cls.upstream, cls.gateway):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            cls.threads.append(thread)

    @classmethod
    def tearDownClass(cls):
        for server in (cls.gateway, cls.upstream):
            server.shutdown()
            server.server_close()
        for thread in cls.threads:
            thread.join(timeout=2)

    def setUp(self):
        self.__class__.requests = []
        self.__class__.status = 200
        self.__class__.payload = b'123456'

    def request(self, method, path=WEBHOOK_PATH, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.gateway.server_port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_only_canonical_webhook_route_is_reachable(self):
        for path in ('/desk', '/login', '/api/resource/User', WEBHOOK_PATH + '/',
                     '/api/method/frappe.client.get_list', WEBHOOK_PATH.replace('/api/', '/%61pi/')):
            with self.subTest(path=path):
                self.assertEqual(self.request('GET', path)[0], 404)
        self.assertEqual(self.requests, [])

    def test_verification_forwards_exact_challenge_without_session_cookies(self):
        path = WEBHOOK_PATH + '?hub.mode=subscribe&hub.verify_token=fictional-token&hub.challenge=123456'
        status, headers, body = self.request('GET', path)
        self.assertEqual((status, body), (200, b'123456'))
        self.assertEqual(self.requests[0][1], path)
        self.assertEqual(self.requests[0][2]['Host'], 'hms.localhost')
        self.assertNotIn('Set-Cookie', headers)
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_signed_payload_is_not_changed_and_browser_credentials_are_dropped(self):
        raw = b'{ "object": "whatsapp_business_account", "entry": [] }\n'
        signature = 'sha256=' + hmac.new(b'fictional-secret', raw, hashlib.sha256).hexdigest()
        status, _, _ = self.request('POST', body=raw, headers={
            'Content-Type': 'application/json', 'X-Hub-Signature-256': signature,
            'Cookie': 'sid=private-session', 'Authorization': 'Bearer private-token',
            'X-Forwarded-Host': 'other.localhost',
        })
        self.assertEqual(status, 200)
        received = self.requests[0]
        self.assertEqual(received[3], raw)
        self.assertEqual(received[2]['X-Hub-Signature-256'], signature)
        self.assertFalse({'cookie', 'authorization', 'x-forwarded-host'} & {k.lower() for k in received[2]})

    def test_meta_verification_aliases_forward_one_canonical_value(self):
        canonical = {'hub.mode': 'subscribe', 'hub.verify_token': 'fictional+token', 'hub.challenge': '123456'}
        aliases = {key.replace('.', '_'): value for key, value in canonical.items()}
        for values in ({**canonical, **aliases}, aliases):
            with self.subTest(keys=list(values)):
                status, _, body = self.request('GET', WEBHOOK_PATH + '?' + urlencode(values))
                self.assertEqual((status, body), (200, b'123456'))
                forwarded = parse_qs(urlsplit(self.requests[-1][1]).query)
                self.assertEqual(forwarded, {key: [value] for key, value in canonical.items()})

    def test_conflicting_verification_aliases_are_rejected(self):
        query = urlencode({'hub.mode': 'subscribe', 'hub_mode': 'other',
                           'hub.challenge': '123456', 'hub.verify_token': 'fictional-token'})
        self.assertEqual(self.request('GET', WEBHOOK_PATH + '?' + query)[0], 400)
        self.assertEqual(self.requests, [])

    def test_query_cannot_override_the_rpc_method(self):
        for method, query in (('GET', 'cmd=frappe.client.get_list'), ('POST', 'cmd=frappe.client.get_list'),
                              ('GET', 'hub.mode=subscribe&hub.mode=subscribe')):
            with self.subTest(method=method, query=query):
                self.assertEqual(self.request(method, WEBHOOK_PATH + '?' + query, body=b'')[0], 400)
        self.assertEqual(self.requests, [])

    def test_other_methods_are_not_forwarded(self):
        for method in ('DELETE', 'PUT', 'PATCH', 'OPTIONS', 'HEAD'):
            self.assertEqual(self.request(method)[0], 405)
        self.assertEqual(self.requests, [])

    def test_oversized_or_ambiguous_payload_is_not_forwarded(self):
        self.assertEqual(self.request('POST', body=b'{}', headers={'Content-Length': str(MAX_BODY + 1)})[0], 413)
        self.assertEqual(self.request('POST', body=b'{}', headers={'Content-Length': '-1'})[0], 400)
        self.assertEqual(self.request('POST', body=b'{}', headers={'Transfer-Encoding': 'chunked'})[0], 400)
        self.assertEqual(self.requests, [])

    def test_application_errors_do_not_publish_debug_output(self):
        self.__class__.status = 500
        self.__class__.payload = b'private debug output must not be exposed'
        status, headers, body = self.request('GET')
        self.assertEqual(status, 500)
        self.assertEqual(body, b'Webhook returned HTTP 500')
        self.assertNotIn('Set-Cookie', headers)

    def test_redirects_are_not_followed_or_published(self):
        self.__class__.status = 302
        self.assertEqual(self.request('GET')[0], 502)
        self.assertEqual(len(self.requests), 1)


if __name__ == '__main__':
    unittest.main()
