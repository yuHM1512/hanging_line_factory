-- 012: Tracking table cho QLCL output sync —
--      ghi nhận (MONo, WorkDate, LastQty) đã push thành công.
--      Incremental sync so sánh MES output vs bảng này để chỉ push dữ liệu thay đổi.

IF OBJECT_ID('app.tOutputSyncLog', 'U') IS NULL
CREATE TABLE app.tOutputSyncLog (
    MONo        nvarchar(100)   NOT NULL,
    WorkDate    date            NOT NULL,
    LastQty     int             NOT NULL,
    SyncedAt    datetime2(0)    NOT NULL
        CONSTRAINT DF_tOutputSyncLog_SyncedAt DEFAULT SYSDATETIME(),
    CONSTRAINT PK_tOutputSyncLog PRIMARY KEY (MONo, WorkDate)
);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_tOutputSyncLog_WorkDate'
      AND object_id = OBJECT_ID('app.tOutputSyncLog')
)
    CREATE INDEX IX_tOutputSyncLog_WorkDate
        ON app.tOutputSyncLog(WorkDate);
GO

PRINT 'Migration 012 applied — output sync log.';
GO
