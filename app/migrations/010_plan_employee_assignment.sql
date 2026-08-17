-- =============================================================
-- Migration 010 - Cache employee assignments by MONo/Odr/Seq
-- =============================================================

IF OBJECT_ID('app.tPlanEmployeeAssignment', 'U') IS NULL
CREATE TABLE app.tPlanEmployeeAssignment (
    Assignment_guid uniqueidentifier NOT NULL CONSTRAINT DF_tPlanEmployeeAssignment_guid DEFAULT NEWID(),
    PlanMaster_guid uniqueidentifier NOT NULL,
    NhuCauMe        nvarchar(100)   NULL,
    RootMONo        nvarchar(100)   NOT NULL,
    SourceMONo      nvarchar(100)   NOT NULL,
    DonVi           nvarchar(50)    NOT NULL,
    [LineNo]        int             NULL,
    BoPhan          nvarchar(50)    NULL,
    WorkLine        nvarchar(50)    NULL,
    StNo            int             NULL,
    Odr             int             NULL,
    SeqNo           nvarchar(50)    NULL,
    SeqName         nvarchar(500)   NULL,
    EmpID           nvarchar(50)    NOT NULL,
    EmpName         nvarchar(200)   NOT NULL,
    Qty             int             NOT NULL CONSTRAINT DF_tPlanEmployeeAssignment_Qty DEFAULT 0,
    FirstWorkDate   date            NULL,
    LastWorkDate    date            NULL,
    SyncedAt        datetime2(0)    NULL,
    UpdatedAt       datetime2(0)    NOT NULL CONSTRAINT DF_tPlanEmployeeAssignment_UpdatedAt DEFAULT SYSDATETIME(),
    CONSTRAINT PK_tPlanEmployeeAssignment PRIMARY KEY (Assignment_guid),
    CONSTRAINT FK_tPlanEmployeeAssignment_PlanMaster FOREIGN KEY (PlanMaster_guid)
        REFERENCES app.tPlanMaster(PlanMaster_guid) ON DELETE CASCADE
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tPlanEmployeeAssignment_Plan' AND object_id = OBJECT_ID('app.tPlanEmployeeAssignment'))
    CREATE INDEX IX_tPlanEmployeeAssignment_Plan ON app.tPlanEmployeeAssignment(PlanMaster_guid);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tPlanEmployeeAssignment_Emp' AND object_id = OBJECT_ID('app.tPlanEmployeeAssignment'))
    CREATE INDEX IX_tPlanEmployeeAssignment_Emp ON app.tPlanEmployeeAssignment(DonVi, EmpID);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_tPlanEmployeeAssignment_Key' AND object_id = OBJECT_ID('app.tPlanEmployeeAssignment'))
    CREATE UNIQUE INDEX UX_tPlanEmployeeAssignment_Key
        ON app.tPlanEmployeeAssignment(PlanMaster_guid, SourceMONo, EmpID, SeqNo, Odr, WorkLine, StNo);
GO

PRINT 'Migration 010 applied - plan employee assignment cache.';
GO
