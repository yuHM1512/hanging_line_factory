-- =============================================================
-- Migration 019 - Flat-line real-time reporting
-- * Assign one operator (mã nhân viên) to each flat operation.
-- * tFlatReport becomes an append-only event log: mỗi lần bấm (+1)
--   là 1 dòng Qty=1 kèm CreatedAt, (-1) xoá dòng mới nhất.
-- * Index để tra dòng mới nhất theo (OperationID, ReportDate) nhanh.
-- =============================================================

IF COL_LENGTH('app.tFlatOperation', 'AssignedEmpID') IS NULL
    ALTER TABLE app.tFlatOperation ADD AssignedEmpID nvarchar(50) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_tFlatReport_Operation_Date'
      AND object_id = OBJECT_ID('app.tFlatReport')
)
    CREATE INDEX IX_tFlatReport_Operation_Date
        ON app.tFlatReport (OperationID, ReportDate) INCLUDE (CreatedAt);
GO

PRINT 'Migration 019 applied - flat-line real-time.';
GO
