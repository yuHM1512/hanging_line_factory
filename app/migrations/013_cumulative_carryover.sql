-- =============================================================
-- Migration 013 - Cumulative carryover for parent demands
-- =============================================================

IF COL_LENGTH('app.tDemandRoot', 'LuyKeChuyenTiep') IS NULL
    ALTER TABLE app.tDemandRoot ADD LuyKeChuyenTiep int NOT NULL
        CONSTRAINT DF_tDemandRoot_LuyKeChuyenTiep DEFAULT (0);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_tDemandRoot_LuyKeChuyenTiep'
      AND parent_object_id = OBJECT_ID('app.tDemandRoot')
)
    ALTER TABLE app.tDemandRoot ADD CONSTRAINT CK_tDemandRoot_LuyKeChuyenTiep
        CHECK (LuyKeChuyenTiep >= 0);
GO

ALTER VIEW app.vDemandRoot AS
SELECT
    dr.NhuCauMe,
    dr.StyleNo,
    dr.DMKT,
    dr.PhanLoaiDH,
    dr.[LineNo],
    dr.LDBienChe,
    dr.LuyKeChuyenTiep,
    dr.Notes,
    dr.CreatedAt, dr.CreatedBy, dr.UpdatedAt, dr.UpdatedBy,
    ISNULL(c.SLKH_Total, 0) AS SLKH,
    ISNULL(c.ChildCount, 0) AS ChildCount,
    c.FirstChildDate AS EarliestFirstHangDate
FROM app.tDemandRoot dr
LEFT JOIN (
    SELECT pm.NhuCauMe,
           SUM(pm.SLKH + ISNULL(adj.AdjustmentQty, 0)) AS SLKH_Total,
           COUNT(*) AS ChildCount,
           MIN(pm.FirstHangDate) AS FirstChildDate
    FROM app.tPlanMaster pm
    OUTER APPLY (
        SELECT SUM(pa.DeltaQty) AS AdjustmentQty
        FROM app.tPlanAdjustment pa
        WHERE pa.PlanMaster_guid = pm.PlanMaster_guid
    ) adj
    WHERE pm.NhuCauMe IS NOT NULL
    GROUP BY pm.NhuCauMe
) c ON c.NhuCauMe = dr.NhuCauMe;
GO

PRINT 'Migration 013 applied - cumulative carryover.';
GO
