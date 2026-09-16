"""Read-only check of the QC API and TV3; no PostgreSQL connection required."""
import sys
from pathlib import Path
from datetime import date
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import flat_sheet, flat_tv


def main():
    verified = 0
    for plan in flat_sheet.snapshot()['plans']:
        if not plan['reports']:
            continue
        day = max(r['day'] for r in plan['reports'])
        qc = flat_sheet.quality(plan['demand'], day)
        if qc['status'] == 'unavailable':
            raise RuntimeError(qc['message'])
        if 'plan_id' not in qc:
            raise RuntimeError('Mother demand missing in QLCL: ' + plan['demand'])
        with patch.object(flat_sheet, 'quality', return_value=qc):
            tv = flat_tv.dashboard(3, 'flat:' + plan['demand'], date.fromisoformat(day))
        assert tv['kpi']['TongLoi'] == (qc['defects'] if qc['status'] == 'ok' else None)
        verified += 1
    if not verified:
        raise RuntimeError('No flat-line reports; sync Sheets first.')
    print('QC API / TV3 verified:', verified, 'mother demands')


if __name__ == '__main__':
    main()
