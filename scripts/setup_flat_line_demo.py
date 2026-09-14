"""Apply only migration 015 and seed the user-requested XN2 demo."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db
from scripts.apply_migrations import GO_RE, MIG_DIR


def main():
    if db.APP_DB.lower() == db.MES_DB.lower():
        raise RuntimeError('App database must be separate from MES')
    with db.get_conn() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        for batch in GO_RE.split((MIG_DIR / '015_flat_line.sql').read_text(encoding='utf-8')):
            if batch.strip():
                cur.execute(batch)
                while cur.nextset():
                    pass
        cur.execute('SELECT [LineNo] FROM app.tDemandRoot WHERE NhuCauMe=?', ('#352847',))
        row = cur.fetchone()
        if not row or row[0] != 3:
            raise RuntimeError('Expected demo demand #352847 / line 3')
        cur.execute('SELECT UserID FROM app.tUser WHERE UserID=?', ('xn2_to3',))
        if not cur.fetchone():
            cur.execute('INSERT INTO app.tUser (UserID,DisplayName,Unit,Dept,Role) VALUES (?,?,?,?,?)', ('xn2_to3','Tổ trưởng XN2 - Tổ 3 (Mẫu)','XN2',3,'user'))
        cur.execute('SELECT ID FROM app.tFlatOperation WHERE NhuCauMe=?', ('#352847',))
        if not cur.fetchone():
            cur.execute('UPDATE app.tDemandRoot SET TrackFlatLine=1 WHERE NhuCauMe=?', ('#352847',))
            for order, name in enumerate(['May lót áo (Mẫu)', 'Chuẩn bị thân áo (Mẫu)', 'Ghép lớp áo (Mẫu)']):
                cur.execute('INSERT INTO app.tFlatOperation (NhuCauMe,Name,SortOrder) OUTPUT INSERTED.ID VALUES (?,?,?)', ('#352847',name,order))
                op_id = cur.fetchone()[0]
                if order == 0:
                    for qty in (200,150):
                        cur.execute('INSERT INTO app.tFlatReport (OperationID,ReportDate,Qty,CreatedBy) VALUES (?,CAST(GETDATE() AS date),?,?)', (op_id,qty,'xn2_to3'))
        conn.commit()
    print('Demo ready: xn2_to3 / #352847 / first operation total 350 pcs on seed date.')


if __name__ == '__main__':
    main()
