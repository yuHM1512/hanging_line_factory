-- =============================================================
-- Migration 009 - Plan quantity adjustments and XN2 line range
-- =============================================================

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_tDemandRoot_LineNo')
    ALTER TABLE app.tDemandRoot DROP CONSTRAINT CK_tDemandRoot_LineNo;
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_tDemandRoot_LineNo')
    ALTER TABLE app.tDemandRoot ADD CONSTRAINT CK_tDemandRoot_LineNo
        CHECK ([LineNo] BETWEEN 1 AND 99);
GO

IF OBJECT_ID('app.tPlanAdjustment', 'U') IS NULL
CREATE TABLE app.tPlanAdjustment (
    Adjustment_guid uniqueidentifier NOT NULL CONSTRAINT PK_tPlanAdjustment PRIMARY KEY
        CONSTRAINT DF_tPlanAdjustment_guid DEFAULT NEWID(),
    PlanMaster_guid uniqueidentifier NOT NULL,
    DeltaQty        int              NOT NULL,
    Reason          nvarchar(100)    NOT NULL,
    Notes           nvarchar(500)    NULL,
    CreatedAt       datetime2(0)     NOT NULL CONSTRAINT DF_tPlanAdjustment_CreatedAt DEFAULT SYSDATETIME(),
    CreatedBy       nvarchar(50)     NULL,
    CONSTRAINT FK_tPlanAdjustment_PlanMaster FOREIGN KEY (PlanMaster_guid)
        REFERENCES app.tPlanMaster(PlanMaster_guid) ON DELETE CASCADE,
    CONSTRAINT CK_tPlanAdjustment_DeltaQty CHECK (DeltaQty <> 0)
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tPlanAdjustment_PlanMaster' AND object_id = OBJECT_ID('app.tPlanAdjustment'))
    CREATE INDEX IX_tPlanAdjustment_PlanMaster ON app.tPlanAdjustment(PlanMaster_guid);
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

PRINT 'Migration 009 applied - plan adjustments and line range.';
GO
