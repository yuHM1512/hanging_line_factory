-- JSON is serialized by the application with json.dumps before persistence.
-- Avoid ISJSON here so this table can also be created on SQL Server 2012/2014.
-- Existing tables (including any existing JSON constraint) are left unchanged.
IF OBJECT_ID('app.tFlatSheetSnapshot', 'U') IS NULL
BEGIN
    CREATE TABLE app.tFlatSheetSnapshot (
        Unit nvarchar(30) NOT NULL PRIMARY KEY,
        Payload nvarchar(max) NOT NULL,
        SyncedAt datetime2 NOT NULL,
        LastAttemptAt datetime2 NOT NULL,
        LastError nvarchar(500) NULL
    );
END;
