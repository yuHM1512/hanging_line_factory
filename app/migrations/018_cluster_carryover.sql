-- =============================================================
-- Migration 018 - Add CarryoverQty to cluster station config
-- Moves cumulative carryover from demand-level to cluster-level.
-- =============================================================

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('app.tClusterStationConfig')
      AND name = 'CarryoverQty'
)
BEGIN
    ALTER TABLE app.tClusterStationConfig
        ADD CarryoverQty int NULL;
END
GO

PRINT 'Migration 018 applied - cluster carryover.';
GO
