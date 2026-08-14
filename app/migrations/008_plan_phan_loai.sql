-- =============================================================
-- Migration 008 — Add LoaiHang to tPlanMaster
-- Loại hàng theo sản phẩm (Áo vest, Quần tây, ...) gắn cho
-- Nhu cầu con, dùng khi sync sang QLCL → prod_plan.loai_hang.
-- Khác với PhanLoaiDH trên tDemandRoot (tính chất ĐH → NĐSX).
-- Idempotent: safe to re-run.
-- =============================================================

-- Thêm cột mới LoaiHang
IF NOT EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('app.tPlanMaster') AND name = 'LoaiHang')
    ALTER TABLE app.tPlanMaster ADD LoaiHang nvarchar(50) NULL;
GO

-- Nếu đã chạy migration cũ với PhanLoaiDH (trên PlanMaster), migrate data rồi drop
IF EXISTS (SELECT 1 FROM sys.columns
           WHERE object_id = OBJECT_ID('app.tPlanMaster') AND name = 'PhanLoaiDH')
BEGIN
    -- Copy data nếu LoaiHang còn NULL
    EXEC sp_executesql N'
        UPDATE app.tPlanMaster
        SET LoaiHang = PhanLoaiDH
        WHERE LoaiHang IS NULL AND PhanLoaiDH IS NOT NULL;

        ALTER TABLE app.tPlanMaster DROP COLUMN PhanLoaiDH;
    ';
END
GO

PRINT N'Migration 008 applied — LoaiHang on tPlanMaster.';
GO
