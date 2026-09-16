IF OBJECT_ID('app.tFlatSheetSnapshot', 'U') IS NULL
BEGIN
    CREATE TABLE app.tFlatSheetSnapshot (
        Unit nvarchar(30) NOT NULL PRIMARY KEY,
        Payload nvarchar(max) NOT NULL,
        SyncedAt datetime2 NOT NULL,
        LastAttemptAt datetime2 NOT NULL,
        LastError nvarchar(500) NULL,
        CONSTRAINT CK_FlatSheetSnapshot_JSON CHECK (ISJSON(Payload)=1)
    );
END;
