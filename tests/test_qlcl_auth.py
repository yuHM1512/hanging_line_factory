import os
import unittest
from datetime import date
from unittest.mock import Mock, patch
from app.tv import _fetch_qlcl_tv3


class QCAuthenticationTests(unittest.TestCase):
    def test_tv_quality_request_uses_server_api_key(self):
        response = Mock()
        response.json.return_value = {'found': True}
        with patch.dict(os.environ, {'QLCL_API_KEY': 'test-only-key'}), patch('app.tv.httpx.get', return_value=response) as get:
            self.assertEqual(_fetch_qlcl_tv3('#123', date(2026,9,15)), {'found': True})
            self.assertEqual(get.call_args.kwargs['headers'], {'X-API-Key':'test-only-key'})
            self.assertEqual(get.call_args.kwargs['params'], {'mono':'#123','date':'2026-09-15'})

    def test_qlcl_failure_retains_unavailable_contract(self):
        with patch('app.tv.httpx.get', side_effect=RuntimeError('unavailable')):
            self.assertEqual(_fetch_qlcl_tv3('#123',date(2026,9,15)), {'found':False})
