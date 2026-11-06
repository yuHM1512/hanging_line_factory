-- =============================================================
-- Migration 020 - Gán tay MONo (MSD, chuyền treo) <-> Nhu cầu mẹ trên Sheet báo cáo 2H
-- TV-3 chuyền treo đọc chất lượng (Data-U2 cột N, Q:AK) theo nhu cầu đã gán
-- trong lúc module QLCL chưa có dữ liệu.
-- =============================================================
IF OBJECT_ID('app.tSheetDemandMap', 'U') IS NULL
BEGIN
    CREATE TABLE app.tSheetDemandMap (
        MONo       nvarchar(100) NOT NULL PRIMARY KEY,
        NhuCauMe   nvarchar(100) NOT NULL,
        UpdatedAt  datetime2     NOT NULL CONSTRAINT DF_tSheetDemandMap_UpdatedAt DEFAULT SYSDATETIME(),
        UpdatedBy  nvarchar(50)  NULL
    );
END;
GO

PRINT 'Migration 020 applied - sheet demand map.';
GO
