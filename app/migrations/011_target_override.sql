-- 011: Hiệu chỉnh lộ trình — cho phép admin override mục tiêu ngày
--      từ 1 ngày (day_n) cụ thể trở đi cho đến khi gặp override tiếp theo.

IF OBJECT_ID('app.tTargetOverride', 'U') IS NULL
CREATE TABLE app.tTargetOverride (
    Override_guid  uniqueidentifier NOT NULL
        CONSTRAINT PK_tTargetOverride PRIMARY KEY
        CONSTRAINT DF_tTargetOverride_guid DEFAULT NEWID(),
    PlanMaster_guid uniqueidentifier NOT NULL,
    DayN            int              NOT NULL,
    TargetQty       int              NOT NULL,
    Notes           nvarchar(200)    NULL,
    CreatedAt       datetime2(0)     NOT NULL
        CONSTRAINT DF_tTargetOverride_CreatedAt DEFAULT SYSDATETIME(),
    CreatedBy       nvarchar(50)     NULL,
    CONSTRAINT FK_tTargetOverride_PlanMaster FOREIGN KEY (PlanMaster_guid)
        REFERENCES app.tPlanMaster(PlanMaster_guid) ON DELETE CASCADE,
    CONSTRAINT CK_tTargetOverride_DayN CHECK (DayN >= 1),
    CONSTRAINT CK_tTargetOverride_TargetQty CHECK (TargetQty > 0),
    CONSTRAINT UQ_tTargetOverride_Plan_DayN UNIQUE (PlanMaster_guid, DayN)
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tTargetOverride_PlanMaster' AND object_id = OBJECT_ID('app.tTargetOverride'))
    CREATE INDEX IX_tTargetOverride_PlanMaster ON app.tTargetOverride(PlanMaster_guid, DayN);
GO
