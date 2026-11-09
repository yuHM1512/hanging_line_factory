-- =============================================================
-- Migration 021 - Flat demand integration for Target Override & Historical Allocation
-- 1. tDemandRoot.Source — distinguish flat_sheet vs manual (hanging)
-- 2. tFlatTargetOverride — target override per NhuCauMe + DayN (flat line)
-- =============================================================

IF COL_LENGTH('app.tDemandRoot', 'Source') IS NULL
    ALTER TABLE app.tDemandRoot ADD Source NVARCHAR(50) NULL;
GO

-- Relax PhanLoaiDH constraint so flat sheet categories can differ
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_tDemandRoot_PhanLoai')
    ALTER TABLE app.tDemandRoot DROP CONSTRAINT CK_tDemandRoot_PhanLoai;
GO

IF OBJECT_ID('app.tFlatTargetOverride', 'U') IS NULL
CREATE TABLE app.tFlatTargetOverride (
    Override_guid   UNIQUEIDENTIFIER NOT NULL
        CONSTRAINT PK_tFlatTargetOverride PRIMARY KEY
        CONSTRAINT DF_tFlatTargetOverride_guid DEFAULT NEWID(),
    NhuCauMe        NVARCHAR(100)    NOT NULL,
    DayN            INT              NOT NULL,
    TargetQty       INT              NOT NULL,
    Notes           NVARCHAR(200)    NULL,
    CreatedAt       DATETIME2(0)     NOT NULL
        CONSTRAINT DF_tFlatTargetOverride_CreatedAt DEFAULT SYSDATETIME(),
    CreatedBy       NVARCHAR(50)     NULL,
    CONSTRAINT UQ_tFlatTargetOverride_Demand_DayN UNIQUE (NhuCauMe, DayN),
    CONSTRAINT CK_tFlatTargetOverride_DayN CHECK (DayN >= 1),
    CONSTRAINT CK_tFlatTargetOverride_TargetQty CHECK (TargetQty > 0)
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tFlatTargetOverride_NhuCauMe' AND object_id = OBJECT_ID('app.tFlatTargetOverride'))
    CREATE INDEX IX_tFlatTargetOverride_NhuCauMe ON app.tFlatTargetOverride(NhuCauMe, DayN);
GO

PRINT 'Migration 021 applied - flat demand integration.';
GO
