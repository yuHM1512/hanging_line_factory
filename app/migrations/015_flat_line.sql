IF COL_LENGTH('app.tDemandRoot', 'TrackFlatLine') IS NULL
    ALTER TABLE app.tDemandRoot ADD TrackFlatLine bit NOT NULL DEFAULT 0;
GO
IF OBJECT_ID('app.tFlatOperation', 'U') IS NULL
CREATE TABLE app.tFlatOperation (
    ID int IDENTITY PRIMARY KEY,
    NhuCauMe nvarchar(100) NOT NULL REFERENCES app.tDemandRoot(NhuCauMe),
    Name nvarchar(200) NOT NULL,
    SortOrder int NOT NULL,
    IsActive bit NOT NULL DEFAULT 1
);
GO
IF OBJECT_ID('app.tFlatReport', 'U') IS NULL
CREATE TABLE app.tFlatReport (
    ID int IDENTITY PRIMARY KEY,
    OperationID int NOT NULL REFERENCES app.tFlatOperation(ID),
    ReportDate date NOT NULL,
    Qty int NOT NULL CHECK (Qty >= 0),
    CreatedBy nvarchar(50) NOT NULL,
    CreatedAt datetime2 NOT NULL DEFAULT SYSDATETIME(),
    UpdatedBy nvarchar(50) NULL,
    UpdatedAt datetime2 NULL
);
GO
IF OBJECT_ID('app.tFlatReportAudit', 'U') IS NULL
CREATE TABLE app.tFlatReportAudit (
    ID int IDENTITY PRIMARY KEY,
    ReportID int NOT NULL REFERENCES app.tFlatReport(ID),
    OldDate date NOT NULL,
    OldQty int NOT NULL,
    NewDate date NOT NULL,
    NewQty int NOT NULL,
    ChangedBy nvarchar(50) NOT NULL,
    ChangedAt datetime2 NOT NULL DEFAULT SYSDATETIME()
);
GO
