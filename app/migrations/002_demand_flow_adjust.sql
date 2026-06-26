-- =============================================================
-- Migration 002 — Adjust demand flow (NhuCauCon first, NhuCauMe second)
-- Idempotent: each ALTER guarded by sys.columns / sys.objects checks.
-- =============================================================

-- (0) Clean stale test row inserted during dev so DROP COLUMN doesn't trip CHECK
DELETE FROM app.tDemandRoot WHERE NhuCauMe = N'#324287AW26-001';
GO

-- (1) tDemandRoot: drop SLKH (mẹ tính từ VIEW sum con)
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_tDemandRoot_SLKH')
    ALTER TABLE app.tDemandRoot DROP CONSTRAINT CK_tDemandRoot_SLKH;
GO

IF EXISTS (SELECT 1 FROM sys.columns
           WHERE object_id = OBJECT_ID('app.tDemandRoot') AND name = 'SLKH')
    ALTER TABLE app.tDemandRoot DROP COLUMN SLKH;
GO

-- (2) tPlanMaster: NhuCauMe → nullable (con tạo trước, gắn mẹ sau)
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_tPlanMaster_DemandRoot')
    ALTER TABLE app.tPlanMaster DROP CONSTRAINT FK_tPlanMaster_DemandRoot;
GO

ALTER TABLE app.tPlanMaster ALTER COLUMN NhuCauMe nvarchar(100) NULL;
GO

ALTER TABLE app.tPlanMaster ADD CONSTRAINT FK_tPlanMaster_DemandRoot
    FOREIGN KEY (NhuCauMe) REFERENCES app.tDemandRoot(NhuCauMe);
GO

-- (3) tPlanMaster: thêm SLKH (sản lượng kế hoạch CON)
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('app.tPlanMaster') AND name = 'SLKH')
    ALTER TABLE app.tPlanMaster ADD SLKH int NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_tPlanMaster_SLKH')
    ALTER TABLE app.tPlanMaster ADD CONSTRAINT CK_tPlanMaster_SLKH
        CHECK (SLKH IS NULL OR SLKH > 0);
GO

-- (4) tPlanMaster: drop EndDateExpected (compute on-read)
IF EXISTS (SELECT 1 FROM sys.columns
           WHERE object_id = OBJECT_ID('app.tPlanMaster') AND name = 'EndDateExpected')
    ALTER TABLE app.tPlanMaster DROP COLUMN EndDateExpected;
GO

-- (5) VIEW: mẹ + SLKH(sum con) + child count
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
    c.FirstChildDate         AS EarliestFirstHangDate
FROM app.tDemandRoot dr
LEFT JOIN (
    SELECT NhuCauMe,
           SUM(SLKH)             AS SLKH_Total,
           COUNT(*)              AS ChildCount,
           MIN(FirstHangDate)    AS FirstChildDate
    FROM app.tPlanMaster
    WHERE NhuCauMe IS NOT NULL
    GROUP BY NhuCauMe
) c ON c.NhuCauMe = dr.NhuCauMe;
GO

PRINT '✓ Migration 002 applied.';
GO
