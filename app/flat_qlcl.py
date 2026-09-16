"""Publish the exact BP daily/milestone totals used by the four TVs."""
import json
import urllib.request


def build_outputs(payload, unit):
    from .flat_sheet import daily_totals
    unit = 'XN1-V1' if unit == 'XN1' else unit
    outputs=[]
    for plan in payload['plans']:
        days={r['day'] for r in plan['reports']}
        for day in sorted(days):
            reports=[r for r in plan['reports'] if r['day']==day]
            previous=0
            slots=[]
            for i in range(5):
                current = daily_totals([r for r in reports if r['slot']<=i])[5] if any(r['slot']==i for r in reports) else None
                slots.append(dict(slot=i+1,qty=current-previous if current is not None else None,cumulative=current))
                if current is not None:
                    previous=current
            outputs.append(dict(source_record_id=unit+':'+plan['demand'],date=day,qty=daily_totals(reports)[5],slots=slots))
    return dict(don_vi=unit,outputs=outputs)


def push(payload):
    from .admin import _qlcl_request
    from .flat_sheet import unit
    request=_qlcl_request('/api/qc/flat-output/push',data=json.dumps(build_outputs(payload,unit())).encode(),method='POST')
    with urllib.request.urlopen(request,timeout=45) as response:
        result=json.loads(response.read())
    if result.get('status')!='ok':
        raise ValueError('QLCL chưa xác nhận nhận sản lượng')
    return result
