import os
import unittest
from unittest.mock import Mock, patch
import httpx
from app.flat_sheet import quality


class FlatQCAPIClientTests(unittest.TestCase):
    def test_remote_url_auth_and_factory_are_used(self):
        payload = dict(status='ok', records=1, defects=2, slots=[], details=[], alerts=[])
        response = Mock()
        response.json.return_value = payload
        with patch.dict(os.environ, {'QLCL_API_URL': 'https://qlcl.example.test/',
                                     'QLCL_API_KEY': 'test-key', 'QLCL_DON_VI': 'XN3'}), patch('httpx.get', return_value=response) as get:
            self.assertEqual(quality('mother', '2026-09-15'), payload)
        self.assertEqual(get.call_args.args[0], 'https://qlcl.example.test/api/tv3/flat-qc-data')
        self.assertEqual(get.call_args.kwargs['headers'], {'X-API-Key': 'test-key'})
        self.assertEqual(get.call_args.kwargs['params'], dict(demand='mother', don_vi='XN3', date='2026-09-15'))
        response.raise_for_status.assert_called_once()

    def test_errors_stay_unknown(self):
        for status in (403, 404, 500):
            response = httpx.Response(status, request=httpx.Request('GET', 'https://example.test'))
            with patch('httpx.get', return_value=response):
                self.assertEqual(quality('mother', '2026-09-15')['status'], 'unavailable')
        with patch('httpx.get', side_effect=httpx.ReadTimeout('timeout')):
            self.assertEqual(quality('mother', '2026-09-15')['status'], 'unavailable')
        for payload in ({'found': False}, [], {'status': 'error'}):
            response = Mock()
            response.json.return_value = payload
            with patch('httpx.get', return_value=response):
                self.assertEqual(quality('mother', '2026-09-15')['status'], 'unavailable')
