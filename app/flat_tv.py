"""Adapt sheet snapshots to the shared four-TV presentation contracts."""
import math
import re
from collections import Counter
from datetime import date, timedelta

from fastapi import HTTPException

from . import flat_sheet
from .quality import inspection

PREFIX = "flat:"


def plans(line_no=None):
    try:
        state = flat_sheet.snapshot()
    except HTTPException as exc:
        if exc.status_code == 503:
            return []
        raise
    result = []
    for p in state['plans']:
        match = re.search(r'L\s*(\d+)', p['team'], re.I)
        if not match:
            continue
        line = int(match[1])
        if line_no is not None and line != line_no:
            continue
        dates = sorted({r['day'] for r in p['reports']})
        result.append(dict(MONo=PREFIX+p['demand'], SoDonHang=p['demand'],
            NhuCauMe=p['demand'], StyleNo=p['style'], LineNoOut=line,
            Customer=p['customer'], SLKH=p['quantity'], FirstHangDate=p['first'],
            ClusterCount=6, DataFrom=dates[0] if dates else None,
            DataTo=dates[-1] if dates else None, IsFlat=True,
            IsActive=bool(dates and dates[-1] >= (date.today()-timedelta(days=7)).isoformat())))
    return result


def pct(actual, target):
    return round(actual / target * 100, 1) if actual is not None and target else None


def dashboard(screen, mono, the_date):
    d = flat_sheet.dashboard_api(mono[len(PREFIX):], the_date.isoformat())
    p, q = d['plan'], d['qc']
    line = re.search(r'L\s*(\d+)', p['team'], re.I)
    header = dict(To=line.group(1) if line else p['team'], MaDonKH=p['demand'],
        MONo=mono, StyleNo=p['style'], Customer=p['customer'], FirstHangDate=p['first'],
        Workers=d['workers'], WIP=d['wip'], TPT=d['tpt'], PhanLoaiDH=p['category'],
        LoaiHang=p['category'], DailyAim=d['target'], ReportDate=d['selected'])
    header['Tổ'] = header['To']
    out = dict(header=header, source='flat_line_sheet', report_date=d['selected'],
        requested_date=d['requested'], cutoff=d['cutoff'], synced_at=d['synced_at'],
        warnings=d['warnings'], sync_error=d['sync_error'], qc_status=q['status'])
    qty, cumulative, target = d['daily'][5], d['cumulative'][5], d['target']
    slot = next((i+1 for i,s in enumerate(d['slots']) if s['label']==d['cutoff']), 0)
    if screen == 1:
        from .tv import _forecast_end_date
        from .admin import get_holidays
        end_actual = _forecast_end_date(date.fromisoformat(p['first']),p['quantity'],qty or 0,cumulative,date.fromisoformat(d['selected']),get_holidays())
        end_target = date.fromisoformat(d['end_target']) if d['end_target'] else None
        out.update(hero=dict(SLKH=p['quantity'], TH=cumulative,
            Remain=max(0,p['quantity']-cumulative), Pct=pct(cumulative,p['quantity'])),
            stats=dict(DayQty=dict(KH=target,TH=qty,Pct=pct(qty,target)),
                Takt=dict(KH=d['takt_target'],TT=d['takt'],Pct=pct(d['takt_target'],d['takt'])),
                OWE=dict(Pct=d['owe'],Target=d['owe_target']),
                DefectRate=dict(Pct=q['rate'],Threshold=5),
                EndDay=dict(Target=date.fromisoformat(d['end_target']).strftime('%d-%m') if d['end_target'] else None,
                    Actual=end_actual.strftime('%d-%m') if end_actual else None,
                    DiffDays=(end_actual-end_target).days if end_actual and end_target else None)),
            hours=[dict(label=s['label'],kh=s['target'],th=s['actual']) for s in d['slots']],
            hdkp=[dict(Slot=i+1,RootCause='',CAPAction='; '.join(a['text'] for a in d['actions'] if a['slot']==s['label'])) for i,s in enumerate(d['slots'])],
            pos=[dict(PONo=x['po'],Qty=x['quantity'],ShipDate=x['date']) for x in p['pos']],
            total_po_qty=sum(x['quantity'] or 0 for x in p['pos']))
    elif screen == 2:
        target_slot = d['target_to_slot']
        header.update(Target=target_slot,TargetFullDay=target,TargetCutoffSlot=slot,TargetCutoffLabel=d['cutoff'])
        out.update(clusters=[dict(Order=i+1,Role='KCS' if i==5 else 'PROD',Label=name,
            RouteStepOdr=i+1,QtyToday=d['daily'][i],Cumulative=d['cumulative'][i],
            Pass=d['daily'][i]>=target_slot if d['daily'][i] is not None and target_slot is not None else None)
            for i,name in enumerate(p['names'])], target=target_slot,target_full_day=target,
            target_cutoff_slot=slot,target_cutoff_label=d['cutoff'],
            y_max=max(50,math.ceil(max([v or 0 for v in d['daily']]+[target_slot or 0])/50)*50))
    elif screen == 3:
        qc_slots = {s['slot']:s['defects'] for s in q.get('slots',[])}
        slots = [dict(slot=i+1,label=s['label'],**inspection(s['actual'],qc_slots.get(i+1,0)))
            for i,s in enumerate(d['slots'])] if q['status']=='ok' else []
        departments, errors = Counter(), Counter()
        combo = []
        for row in q.get('details',[]):
            departments[row['department']] += row['quantity']
            errors[row['defect']] += row['quantity']
            combo.append(dict(bp=row['department'],ct=row['detail'],ma_loi=row['defect'],n=row['quantity']))
        counts = inspection(qty, q.get('defects') if q['status']=='ok' else None)
        out.update(kpi=dict(TongDat=qty,TongKiem=counts['kiem'],TongLoi=counts['loi'],TyLeLoi=counts['pct'],
            DefectTarget5=5,DefectStatus=('pass' if counts['pct']<=5 else 'fail') if counts['pct'] is not None else None,
            CanhBaoCount=len(q['alerts']) if 'alerts' in q else None,CurrentSlot=slot,MES_KCS_Qty=qty,FinalClusterQty=qty),
            slots=slots,bo_phan=[dict(name=k,count=v) for k,v in departments.items()],
            top3=[dict(ma_loi=k,n=v) for k,v in errors.most_common(3)],combo=combo,canh_bao=q.get('alerts',[]),qc_source='qlcl')
    elif screen == 4:
        from .tv import _workday_index, _ndsx_level
        from .admin import get_holidays
        holidays = get_holidays()
        first = date.fromisoformat(p['first'])
        seconds = 29520/(p['workers']*p['dmkt'])
        days=[]
        for row in d['schedule']:
            dt=date.fromisoformat(row['day'])
            n=_workday_index(first,dt,holidays) if dt>=first else 0
            days.append(dict(DayN=n,DayLabel=dt.strftime('%d/%m') if dt<first else str(n),Date=row['day'],Workers=row['workers'],TargetNS=row['target'],
                Actual=row['actual'],CumTarget=row['cum_target'],CumActual=row['cum_actual'],
                Ratio=row['target']/(p['dmkt']*row['workers']) if row['target'] is not None and row['workers'] else None,
                Pct=pct(row['actual'],row['target']),IsPast=row['day']<=d['selected'],IsCurrent=row['day']==d['selected']))
        header.update(SLKH=p['quantity'],DMKT=p['dmkt'],NDSXSec=seconds,NDSXLevel=_ndsx_level(p['category'],seconds),
            LDBienChe=p['workers'],SoCaKH=next((r['DayN'] for r in days if r['Date']==d['end_target']),None),
            DayRatio1=next((r['DayN'] for r in days if r['Ratio'] is not None and r['Ratio']>=1),None))
        out.update(days=days,current_day_n=next((r['DayN'] for r in days if r['IsCurrent']),None))
    return out
