"""QC totals: production output is passed garments, not total inspected."""


def inspection(passed, defects):
    # Missing counts and negative milestone corrections cannot establish a rate.
    total = passed + defects if passed is not None and defects is not None and passed >= 0 and defects >= 0 else None
    rate = round(defects / total * 100, 1) if total is not None and total > 0 else None
    return dict(dat=passed, loi=defects, kiem=total, pct=rate)
