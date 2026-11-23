-- =============================================================
-- Migration 022 - Nhu cầu con (child demand) trên tPlanAdjustment
-- =============================================================
-- Một "nhu cầu con" = 1 dòng tPlanAdjustment có DemandNo + ProdDate.
--   * DeltaQty (> 0) cộng vào SLKH giống mọi lần tăng/giảm → mọi chỗ
--     đang SUM(DeltaQty) tự tính đúng, không cần sửa.
--   * TV-1 "Nhu cầu mới nhất" theo ngày xem D = DemandNo có ProdDate
--     lớn nhất mà <= D (chưa tới ngày SX thì vẫn hiện nhu cầu con cũ).
-- Dòng tăng/giảm thường giữ DemandNo/ProdDate = NULL.

IF COL_LENGTH('app.tPlanAdjustment', 'DemandNo') IS NULL
    ALTER TABLE app.tPlanAdjustment ADD DemandNo nvarchar(100) NULL;
GO

IF COL_LENGTH('app.tPlanAdjustment', 'ProdDate') IS NULL
    ALTER TABLE app.tPlanAdjustment ADD ProdDate date NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_tPlanAdjustment_ChildDemand')
    ALTER TABLE app.tPlanAdjustment ADD CONSTRAINT CK_tPlanAdjustment_ChildDemand
        CHECK (
            (DemandNo IS NULL AND ProdDate IS NULL)
            OR (DemandNo IS NOT NULL AND ProdDate IS NOT NULL AND DeltaQty > 0)
        );
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_tPlanAdjustment_ChildDemand' AND object_id = OBJECT_ID('app.tPlanAdjustment'))
    CREATE INDEX IX_tPlanAdjustment_ChildDemand
        ON app.tPlanAdjustment(PlanMaster_guid, ProdDate)
        INCLUDE (DemandNo);
GO
