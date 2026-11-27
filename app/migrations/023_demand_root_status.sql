-- Migration 023: Add Status column to tDemandRoot + rebuild vDemandRoot
-- Status: 'active' (default) | 'finished'

IF COL_LENGTH('app.tDemandRoot', 'Status') IS NULL
    ALTER TABLE app.tDemandRoot ADD [Status] NVARCHAR(20) NOT NULL
        CONSTRAINT DF_tDemandRoot_Status DEFAULT ('active');
GO

IF OBJECT_ID('app.vDemandRoot', 'V') IS NOT NULL
    DROP VIEW app.vDemandRoot;
GO

CREATE VIEW app.vDemandRoot AS
SELECT
    dr.NhuCauMe,
    dr.StyleNo,
    dr.DMKT,
    dr.PhanLoaiDH,
    dr.[LineNo],
    dr.LDBienChe,
    dr.LuyKeChuyenTiep,
    dr.Notes,
    dr.[Status],
    dr.Source,
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

PRINT 'Migration 023 applied - DemandRoot status column.';
