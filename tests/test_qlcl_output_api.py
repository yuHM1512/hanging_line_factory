"""GET /api/qlcl/hanging-output — QLCL kéo sản lượng ra chuyền (giống TV-1, cụm 6, mọi bàn QC)."""
import unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import qlcl_output_api

KEY = 'test-only-key'
MONO = 'PL-26-351265-SS27-016'


class QLCLOutputApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(qlcl_output_api.router)
        self.client = TestClient(app)
        key_patch = patch.object(qlcl_output_api, 'QLCL_API_KEY', KEY)
        key_patch.start()
        self.addCleanup(key_patch.stop)

    def get(self, key=KEY, **params):
        query = {'mono': MONO, 'date': '2026-11-26', **params}
        headers = {'X-API-Key': key} if key is not None else {}
        return self.client.get('/api/qlcl/hanging-output', params=query, headers=headers)

    def test_returns_cluster6_output_for_all_qc_tables(self):
        with patch('app.tv._tv1_qc_filter', return_value=(104, None)) as qc_filter, \
                patch('app.tv._output_kcs', return_value={'Qty': 182, 'Def': 3}) as kcs:
            response = self.get()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            'mono': MONO, 'date': '2026-11-26', 'qty': 182, 'defective_qty': 3, 'seq_no': 104, 'st_no': None,
        })
        qc_filter.assert_called_once_with(MONO)
        # Một ngày, cùng bước cụm 6, StNo=None → cộng mọi bàn QC (như TV-1).
        kcs.assert_called_once_with(MONO, date(2026, 11, 26), date(2026, 11, 26), (104, None))

    def test_plan_without_qc_step_returns_zero(self):
        with patch('app.tv._tv1_qc_filter', return_value=(None, None)), \
                patch('app.tv._output_kcs') as kcs:
            response = self.get()
        self.assertEqual(response.json()['qty'], 0)
        kcs.assert_not_called()

    def test_requires_matching_key(self):
        with patch('app.tv._tv1_qc_filter') as qc_filter:
            self.assertEqual(self.get(key='wrong').status_code, 403)
            self.assertEqual(self.get(key=None).status_code, 403)
        qc_filter.assert_not_called()

    def test_rejects_when_server_key_not_configured(self):
        with patch.object(qlcl_output_api, 'QLCL_API_KEY', ''):
            self.assertEqual(self.get(key='').status_code, 403)

    def test_validates_parameters(self):
        self.assertEqual(self.get(date='26/11/2026').status_code, 422)
        self.assertEqual(self.client.get('/api/qlcl/hanging-output', params={'date': '2026-11-26'},
                                         headers={'X-API-Key': KEY}).status_code, 422)

    def test_registered_in_main_app(self):
        source = Path('app/main.py').read_text(encoding='utf-8')
        self.assertIn('app.include_router(qlcl_output_api.router)', source)


if __name__ == '__main__':
    unittest.main()
