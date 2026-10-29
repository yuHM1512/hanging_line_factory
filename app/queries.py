"""SQL query templates for the hanging-line dashboard.

All queries follow the golden rule in CLAUDE.md:
    "Hàng ra chuyền" = StRole = 13 AND IsLastSeq = 1.

"Tổ" on the dashboard is the logical line parsed from MONo:
    LINE 1 ... -> Tổ 1
    LINE 6 ... -> Tổ 6

Physical LineNo rows are kept and aggregated into the logical line above.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .db import query


NORMALIZED_WORK_CTE = """
    ;WITH NormalizedWork AS (
        SELECT
            rw.*,
            st.StRole AS station_role,
            st.StNo AS station_no_src,
            st.RailNo AS rail_no_src,
            TRY_CONVERT(
                int,
                LEFT(
                    mo3.digit_tail,
                    PATINDEX('%[^0-9]%', ISNULL(mo3.digit_tail, '') + 'X') - 1
                )
            ) AS logical_line_no,
            CASE
                WHEN CHARINDEX('#', rw.MONo) > 0 THEN SUBSTRING(rw.MONo, CHARINDEX('#', rw.MONo), 200)
            END AS plan_key
        FROM {MES_DB}.dbo.tRecentWork rw
        INNER JOIN {MES_DB}.dbo.tStation st ON rw.Station_guid = st.guid
        OUTER APPLY (
            SELECT CASE
                WHEN PATINDEX('%LINE%', UPPER(rw.MONo)) > 0
                    THEN SUBSTRING(rw.MONo, PATINDEX('%LINE%', UPPER(rw.MONo)) + 4, 200)
            END AS mo_tail
        ) mo1
        OUTER APPLY (
            SELECT CASE
                WHEN NULLIF(PATINDEX('%[0-9]%', ISNULL(mo1.mo_tail, '')), 0) IS NOT NULL
                    THEN SUBSTRING(
                        mo1.mo_tail,
                        NULLIF(PATINDEX('%[0-9]%', ISNULL(mo1.mo_tail, '')), 0),
                        32
                    )
            END AS digit_tail
        ) mo3
        WHERE CAST(rw.BeginTime AS DATE) = rw.ShtDate
    )
"""


def _base_where(alias: str, params: list[Any], line_no: int | None = None, plan_key: str | None = None) -> str:
    where = f"""
        WHERE {alias}.station_role = 13
          AND {alias}.IsLastSeq = 1
          AND {alias}.logical_line_no IS NOT NULL
    """
    if line_no is not None:
        where += f" AND {alias}.logical_line_no = ?"
        params.append(line_no)
    if plan_key:
        where += f" AND {alias}.plan_key = ?"
        params.append(plan_key)
    return where


# ---------- Filter helpers ---------- #
def list_lines() -> list[dict]:
    """Available logical lines for the hanging-line dashboard."""
    return [{"line_no": 1}, {"line_no": 6}]


def list_plans(
    date_from: date, date_to: date, line_no: int | None = None
) -> list[dict]:
    params: list[Any] = []
    where = _base_where("nw", params, line_no=line_no)
    params.extend([date_from, date_to])
    sql = f"""
        {NORMALIZED_WORK_CTE}
        SELECT
            nw.plan_key AS plan_key,
            MIN(nw.MONo) AS mo_no,
            MIN(nw.StyleNo) AS style_no,
            MIN(nw.logical_line_no) AS line_no
        FROM NormalizedWork nw
        {where}
          AND nw.ShtDate BETWEEN ? AND ?
          AND nw.plan_key IS NOT NULL
        GROUP BY nw.plan_key
        ORDER BY MIN(nw.logical_line_no), nw.plan_key;
    """
    return query(sql, params)


def date_bounds() -> dict:
    sql = f"""
        {NORMALIZED_WORK_CTE}
        SELECT MIN(nw.ShtDate) AS min_date, MAX(nw.ShtDate) AS max_date
        FROM NormalizedWork nw
        WHERE nw.station_role = 13
          AND nw.IsLastSeq = 1
          AND nw.logical_line_no IS NOT NULL;
    """
    rows = query(sql)
    return rows[0] if rows else {"min_date": None, "max_date": None}


# ---------- KPI summary ---------- #
def kpi_summary(
    date_from: date, date_to: date, line_no: int | None = None, plan_key: str | None = None
) -> dict:
    params: list[Any] = []
    where = _base_where("nw", params, line_no=line_no, plan_key=plan_key)
    params.extend([date_from, date_to])
    sql = f"""
        {NORMALIZED_WORK_CTE}
        SELECT
            ISNULL(SUM(nw.Qty), 0)                  AS output_qty,
            ISNULL(SUM(nw.DefectiveQty), 0)         AS defect_qty,
            COUNT(DISTINCT nw.logical_line_no)      AS lines_active,
            COUNT(DISTINCT nw.plan_key)             AS plans_active,
            COUNT(DISTINCT nw.ShtDate)              AS days_active,
            COUNT(DISTINCT nw.EmpID)                AS workers_active
        FROM NormalizedWork nw
        {where}
          AND nw.ShtDate BETWEEN ? AND ?;
    """
    rows = query(sql, params)
    return rows[0] if rows else {}


# ---------- Output time series ---------- #
def output_by_day(
    date_from: date, date_to: date, line_no: int | None = None, plan_key: str | None = None
) -> list[dict]:
    params: list[Any] = []
    where = _base_where("nw", params, line_no=line_no, plan_key=plan_key)
    params.extend([date_from, date_to])
    sql = f"""
        {NORMALIZED_WORK_CTE}
        SELECT
            CONVERT(varchar(10), nw.ShtDate, 120) AS day,
            nw.logical_line_no                    AS line_no,
            SUM(nw.Qty)                           AS output_qty,
            SUM(nw.DefectiveQty)                  AS defect_qty
        FROM NormalizedWork nw
        {where}
          AND nw.ShtDate BETWEEN ? AND ?
        GROUP BY nw.ShtDate, nw.logical_line_no
        ORDER BY nw.ShtDate, nw.logical_line_no;
    """
    return query(sql, params)


def output_by_hour(
    date_from: date, date_to: date, line_no: int | None = None, plan_key: str | None = None
) -> list[dict]:
    params: list[Any] = []
    where = _base_where("nw", params, line_no=line_no, plan_key=plan_key)
    params.extend([date_from, date_to])
    sql = f"""
        {NORMALIZED_WORK_CTE}
        SELECT
            nw.logical_line_no                  AS line_no,
            DATEPART(HOUR, nw.BeginTime)        AS hour,
            SUM(nw.Qty)                         AS output_qty
        FROM NormalizedWork nw
        {where}
          AND nw.ShtDate BETWEEN ? AND ?
        GROUP BY nw.logical_line_no, DATEPART(HOUR, nw.BeginTime)
        ORDER BY nw.logical_line_no, hour;
    """
    return query(sql, params)


SHIFT_SLOTS = [
    (1, "07:30 – 09:30"),
    (2, "09:30 – 11:30"),
    (3, "12:30 – 14:30"),
    (4, "14:30 – 16:30"),
    (5, "Sau 16:30"),
]


def output_by_slot(
    date_from: date, date_to: date, line_no: int | None = None, plan_key: str | None = None
) -> list[dict]:
    params: list[Any] = []
    where = _base_where("nw", params, line_no=line_no, plan_key=plan_key)
    params.extend([date_from, date_to])
    sql = f"""
        {NORMALIZED_WORK_CTE}
        , Bucket AS (
            SELECT
                nw.logical_line_no AS line_no,
                nw.Qty,
                CASE
                    WHEN CAST(nw.BeginTime AS time) >= '07:30'
                     AND CAST(nw.BeginTime AS time) <  '09:30' THEN 1
                    WHEN CAST(nw.BeginTime AS time) >= '09:30'
                     AND CAST(nw.BeginTime AS time) <  '11:30' THEN 2
                    WHEN CAST(nw.BeginTime AS time) >= '12:30'
                     AND CAST(nw.BeginTime AS time) <  '14:30' THEN 3
                    WHEN CAST(nw.BeginTime AS time) >= '14:30'
                     AND CAST(nw.BeginTime AS time) <  '16:30' THEN 4
                    WHEN CAST(nw.BeginTime AS time) >= '16:30' THEN 5
                END AS slot
            FROM NormalizedWork nw
            {where}
              AND nw.ShtDate BETWEEN ? AND ?
        )
        SELECT line_no, slot, SUM(Qty) AS output_qty
        FROM Bucket
        WHERE slot IS NOT NULL
        GROUP BY line_no, slot
        ORDER BY line_no, slot;
    """
    return query(sql, params)


def output_by_line(date_from: date, date_to: date, plan_key: str | None = None) -> list[dict]:
    params: list[Any] = []
    where = _base_where("nw", params, plan_key=plan_key)
    params.extend([date_from, date_to])
    sql = f"""
        {NORMALIZED_WORK_CTE}
        SELECT
            nw.logical_line_no              AS line_no,
            SUM(nw.Qty)                     AS output_qty,
            SUM(nw.DefectiveQty)            AS defect_qty
        FROM NormalizedWork nw
        {where}
          AND nw.ShtDate BETWEEN ? AND ?
        GROUP BY nw.logical_line_no
        ORDER BY nw.logical_line_no;
    """
    return query(sql, params)


# ---------- Plan breakdown ---------- #
def output_by_plan(
    date_from: date, date_to: date, line_no: int | None = None, plan_key: str | None = None
) -> list[dict]:
    params: list[Any] = []
    where = _base_where("nw", params, line_no=line_no, plan_key=plan_key)
    params.extend([date_from, date_to])
    sql = f"""
        {NORMALIZED_WORK_CTE}
        SELECT
            CONVERT(varchar(10), nw.ShtDate, 120) AS day,
            nw.plan_key                           AS plan_key,
            nw.MONo                               AS mo_no,
            nw.StyleNo                            AS style_no,
            nw.PONo                               AS po_no,
            nw.ColorNo                            AS color_no,
            nw.SizeNo                             AS size_no,
            nw.logical_line_no                    AS line_no,
            SUM(nw.Qty)                           AS output_qty,
            SUM(nw.DefectiveQty)                  AS defect_qty
        FROM NormalizedWork nw
        {where}
          AND nw.ShtDate BETWEEN ? AND ?
        GROUP BY
            nw.ShtDate, nw.plan_key, nw.MONo, nw.StyleNo, nw.PONo,
            nw.ColorNo, nw.SizeNo, nw.logical_line_no
        ORDER BY nw.ShtDate DESC, nw.logical_line_no, nw.plan_key, nw.ColorNo, nw.SizeNo;
    """
    return query(sql, params)


# ---------- Worker productivity (per Worker × StNo) ---------- #
def worker_productivity(
    date_from: date, date_to: date, line_no: int | None = None, plan_key: str | None = None
) -> list[dict]:
    params: list[Any] = []
    where_inner = _base_where("nw", params, line_no=line_no, plan_key=plan_key)
    params.extend([date_from, date_to])
    sql = f"""
        {NORMALIZED_WORK_CTE}
        , PerSeq AS (
            SELECT
                nw.ShtDate,
                nw.MONo,
                nw.StyleNo,
                nw.ColorNo,
                nw.SizeNo,
                nw.plan_key,
                nw.logical_line_no,
                nw.station_no_src,
                nw.EmpID,
                nw.EmpName,
                nw.SeqNo,
                COUNT(*)              AS qty_per_seq,
                SUM(nw.RealMinute)    AS minute_per_seq,
                SUM(nw.DefectiveQty)  AS defect_per_seq,
                AVG(nw.SAM)           AS sam_per_seq
            FROM NormalizedWork nw
            {where_inner}
              AND nw.ShtDate BETWEEN ? AND ?
            GROUP BY
                nw.ShtDate, nw.MONo, nw.StyleNo, nw.ColorNo, nw.SizeNo,
                nw.plan_key, nw.logical_line_no, nw.station_no_src, nw.EmpID, nw.EmpName, nw.SeqNo
        )
        SELECT
            CONVERT(varchar(10), ShtDate, 120) AS day,
            plan_key                           AS plan_key,
            MONo                               AS mo_no,
            StyleNo                            AS style_no,
            ColorNo                            AS color_no,
            SizeNo                             AS size_no,
            logical_line_no                    AS line_no,
            station_no_src                     AS station_no,
            EmpID                              AS emp_id,
            EmpName                            AS emp_name,
            COUNT(DISTINCT SeqNo)              AS seq_count,
            MAX(qty_per_seq)                   AS output_qty,
            SUM(defect_per_seq)                AS defect_qty,
            SUM(sam_per_seq * qty_per_seq)     AS total_sam,
            CAST(SUM(minute_per_seq) AS decimal(10,2)) AS real_minute,
            CASE WHEN SUM(minute_per_seq) = 0 THEN 0
                 ELSE CAST(SUM(sam_per_seq * qty_per_seq) / SUM(minute_per_seq) AS decimal(10,3))
            END                                AS efficiency
        FROM PerSeq
        GROUP BY
            ShtDate, plan_key, MONo, StyleNo, ColorNo, SizeNo,
            logical_line_no, station_no_src, EmpID, EmpName
        ORDER BY ShtDate DESC, logical_line_no, station_no_src, EmpID;
    """
    return query(sql, params)


# ---------- Final station per plan ---------- #
def final_stations(date_from: date, date_to: date, plan_key: str | None = None) -> list[dict]:
    params: list[Any] = []
    where = _base_where("nw", params, plan_key=plan_key)
    params.extend([date_from, date_to])
    sql = f"""
        {NORMALIZED_WORK_CTE}
        SELECT DISTINCT
            nw.plan_key         AS plan_key,
            nw.MONo             AS mo_no,
            nw.SeqNo            AS seq_no,
            nw.SeqName          AS seq_name,
            nw.logical_line_no  AS line_no,
            nw.rail_no_src      AS rail_no,
            nw.station_no_src   AS station_no
        FROM NormalizedWork nw
        {where}
          AND nw.ShtDate BETWEEN ? AND ?
        ORDER BY nw.plan_key, nw.logical_line_no, nw.rail_no_src, nw.station_no_src;
    """
    return query(sql, params)
