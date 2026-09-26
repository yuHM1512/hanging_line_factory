-- =============================================================
-- Migration 017 - Add AllocationDate to historical output allocation
-- Allows per-day overtime allocation instead of per-demand only.
-- =============================================================

-- Step 1: Add AllocationDate column (nullable at first for existing rows)
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('app.tHistoricalOutputAllocation')
      AND name = 'AllocationDate'
)
BEGIN
    ALTER TABLE app.tHistoricalOutputAllocation
        ADD AllocationDate date NULL;
END
GO

-- Step 2: Drop old PK (single column on NhuCauMe)
IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE name = 'PK_tHistoricalOutputAllocation'
      AND parent_object_id = OBJECT_ID('app.tHistoricalOutputAllocation')
)
BEGIN
    ALTER TABLE app.tHistoricalOutputAllocation
        DROP CONSTRAINT PK_tHistoricalOutputAllocation;
END
GO

-- Step 3: Create composite PK on (NhuCauMe, AllocationDate)
--         Existing rows with NULL date get a sentinel '1900-01-01' so PK can be NOT NULL.
UPDATE app.tHistoricalOutputAllocation
SET AllocationDate = '1900-01-01'
WHERE AllocationDate IS NULL;
GO

ALTER TABLE app.tHistoricalOutputAllocation
    ALTER COLUMN AllocationDate date NOT NULL;
GO

ALTER TABLE app.tHistoricalOutputAllocation
    ADD CONSTRAINT PK_tHistoricalOutputAllocation
        PRIMARY KEY (NhuCauMe, AllocationDate);
GO

PRINT 'Migration 017 applied - historical allocation date dimension.';
GO
