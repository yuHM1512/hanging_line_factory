"""Endline quality from the 2-hour Sheet report — temporary TV-3 source while QLCL is unfinished.

Data-U2 columns used (0-based index in the A:BV read):
    N  (13)       SỐ LỖI (KHÔNG LŨY KẾ) — defective garments of the milestone
    Q:AJ (16-35)  5 groups × [Lỗi, Trạm mắc lỗi, Lỗi ứng với từng trạm, Hành động khắc phục]
    AK (36)       Số lượng sau khi sửa chữa kiểm tra lại đạt yêu cầu

Mirrors the "3. Tx" dashboard tab of the Sheet:
    table/2H   = rows of the latest reported milestone (16H30 + Sau 16H30 at end of day)
    Lũy kế     = sum over every milestone of the report day
    Top 3      = defect types ranked by cumulative quantity of the day
"""
from __future__ import annotations

import re

DEFECT_COUNT_COL = 13
FIRST_DEFECT_COL = 16
DEFECT_GROUPS = 5
REINSPECT_COL = 36
TABLE_ROWS = 5
LAST_FULL_SLOT = 3  # "16H30"; index 4 is "Sau 16H30"

_TOKENS = re.compile(r"[,;.\s/]+")
_LEADING_INT = re.compile(r"\d+")


def _cell(row, i):
    return str(row[i]).strip() if i < len(row) and row[i] is not None else ""


def _amount(value):
    """Lenient numeric cell: free text must never break the production sync."""
    text = str(value or "").replace(",", "").strip()
    if not text or text.startswith("#"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _tokens(value):
    return [t for t in _TOKENS.split(str(value or "")) if t]


def parse_row(row):
    """Quality block of one Data-U2 row."""
    defects = []
    for g in range(DEFECT_GROUPS):
        base = FIRST_DEFECT_COL + 4 * g
        kind = _cell(row, base)
        if not kind:
            continue
        stations = _tokens(_cell(row, base + 1))
        counts = [int(m.group()) for m in map(_LEADING_INT.match, _tokens(_cell(row, base + 2))) if m]
        defects.append(dict(type=kind, stations=stations, counts=counts, cap=_cell(row, base + 3)))
    return dict(defects=defects, defect_qty=_amount(_cell(row, DEFECT_COUNT_COL)),
                reinspect=_amount(_cell(row, REINSPECT_COL)))


def defect_qty(defect):
    # A named defect type without a count still means at least one defective garment.
    return sum(defect["counts"]) if defect["counts"] else 1


def positions(defect):
    """'Trạm 33: 1 lỗi' per station; a single total over several stations stays combined."""
    stations, counts = defect["stations"], defect["counts"]
    if not stations:
        return []
    if len(counts) == len(stations):
        return [f"Trạm {s}: {c} lỗi" for s, c in zip(stations, counts)]
    return [f"Trạm {', '.join(stations)}: {defect_qty(defect)} lỗi"]


def _total(values):
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def _blocks(reports):
    return [r.get("quality") or dict(defects=[], defect_qty=None, reinspect=None) for r in reports]


def window_slots(cutoff):
    """Milestones shown as 'last 2H'. Lines list defect types at 16H30 and post the end-of-day
    re-inspection at 'Sau 16H30', so the final window joins both (the Sheet shows 16H30 after 16:30)."""
    if cutoff < 0:
        return set()
    return {LAST_FULL_SLOT, cutoff} if cutoff > LAST_FULL_SLOT else {cutoff}


def summarize(reports, cutoff):
    """Quality of one report day; `cutoff` is the latest reported milestone index (-1 = none)."""
    day_blocks = _blocks(reports)
    window = window_slots(cutoff)
    window_blocks = _blocks([r for r in reports if r["slot"] in window])

    rows = {}
    for block in window_blocks:
        for d in block["defects"]:
            row = rows.setdefault(d["type"], dict(type=d["type"], positions=[], qty=0, cap=[]))
            row["positions"] += positions(d)
            row["qty"] += defect_qty(d)
            if d["cap"] and d["cap"] not in row["cap"]:
                row["cap"].append(d["cap"])
    table = sorted(rows.values(), key=lambda r: -r["qty"])

    ranking = {}
    for block in day_blocks:
        for d in block["defects"]:
            ranking[d["type"]] = ranking.get(d["type"], 0) + defect_qty(d)
    top3 = [dict(type=k, qty=v) for k, v in sorted(ranking.items(), key=lambda kv: -kv[1])[:3]]

    # N is the defect count the line reports for every milestone, even when Q:AJ is left blank;
    # fall back to the parsed defect groups only when N itself is missing.
    def defects_of(blocks):
        reported = _total(b["defect_qty"] for b in blocks)
        if reported is not None:
            return reported
        parsed = [defect_qty(d) for b in blocks for d in b["defects"]]
        return sum(parsed) if parsed else None

    defects_2h = defects_of(window_blocks)
    reinspect_2h = _total(b["reinspect"] for b in window_blocks)
    defects_day = defects_of(day_blocks)
    reinspect_day = _total(b["reinspect"] for b in day_blocks)
    has_data = any(b["defects"] or b["defect_qty"] is not None or b["reinspect"] is not None for b in day_blocks)
    from .flat_sheet import SLOTS
    return dict(
        status="ok" if has_data else "empty",
        source="sheet",
        window=SLOTS[cutoff] if cutoff >= 0 else None,
        rows=[dict(r, cap="; ".join(r["cap"])) for r in table[:TABLE_ROWS]],
        more_rows=max(0, len(table) - TABLE_ROWS),
        top3=top3,
        defects_2h=defects_2h,
        reinspect_2h=reinspect_2h,
        reinspect_rate=round(reinspect_2h / defects_2h * 100, 1) if defects_2h and reinspect_2h is not None else None,
        defects_day=defects_day,
        reinspect_day=reinspect_day,
        # Same key the QLCL response used, so TV-1's defect rate keeps working.
        defects=defects_day,
    )
