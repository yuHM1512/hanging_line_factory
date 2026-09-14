-- =============================================================
-- Migration 014 - Overtime ratio for historical output allocation
-- =============================================================

IF OBJECT_ID('app.tHistoricalOutputAllocation', 'U') IS NULL
CREATE TABLE app.tHistoricalOutputAllocation (
    NhuCauMe         nvarchar(100) NOT NULL
        CONSTRAINT PK_tHistoricalOutputAllocation PRIMARY KEY,
    OvertimePercent  decimal(5,2)  NOT NULL,
    Notes            nvarchar(200) NULL,
    UpdatedAt        datetime2(0)  NOT NULL
        CONSTRAINT DF_tHistoricalOutputAllocation_UpdatedAt DEFAULT SYSDATETIME(),
    UpdatedBy        nvarchar(50)  NULL,
    CONSTRAINT FK_tHistoricalOutputAllocation_DemandRoot FOREIGN KEY (NhuCauMe)
        REFERENCES app.tDemandRoot(NhuCauMe) ON DELETE CASCADE,
    CONSTRAINT CK_tHistoricalOutputAllocation_Percent
        CHECK (OvertimePercent >= 0 AND OvertimePercent <= 100)
);
GO

PRINT 'Migration 014 applied - historical output allocation.';
GO
