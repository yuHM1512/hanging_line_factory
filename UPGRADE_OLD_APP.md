# Upgrade app cu sang flow Nhu cau me moi

Tai lieu nay dung cho truong hop:

- app hanging da chay tu truoc
- database app nhu `hanging_app`, `hanging_app_XN2`, `hanging_app_XN3` dang co schema cu
- trong DB dang co du lieu setup nhu cau theo flow cu
- can nang cap sang flow moi:
  - setup theo `NhuCauMe`
  - co `tPlanAdjustment`
  - co `tPlanEmployeeAssignment`
  - sync nhan su sang QLCL theo `MONo` goc
  - chi sync cong doan co `StRole = 13`

## 1. Khi nao dung tai lieu nay

Dung tai lieu nay khi:

- app cu da tung khai bao Nhu cau me / con
- trong DB app dang co setup ke hoach cu
- muon don sach du lieu setup cu de nhap lai theo flow moi

Khong dung tai lieu nay neu:

- ban dang cai app moi tinh tren may moi
- DB app chua co du lieu setup nao

Neu cai moi tinh, dung `SETUP.md`.

## 2. Backup DB app truoc khi nang cap

Nen backup truoc khi xoa du lieu setup cu:

```sql
BACKUP DATABASE [hanging_app]
TO DISK = 'C:\Backup\hanging_app_before_upgrade.bak'
WITH INIT, COMPRESSION;
```

Doi lai ten DB va duong dan `.bak` cho dung may.

## 3. Xoa du lieu setup nhu cau cu

Chay SQL nay trong DB app hanging. SQL nay chi don phan setup nhu cau va cache lien quan, khong dung toi user, holiday, SAM.

Luu y:

- DB cu co the chua co `app.tPlanAdjustment`
- DB cu co the chua co `app.tPlanEmployeeAssignment`
- vi vay can dung script xoa co kiem tra ton tai bang truoc khi `DELETE`

```sql
BEGIN TRAN;

IF OBJECT_ID('app.tClusterStationConfig', 'U') IS NOT NULL
    SELECT 'tClusterStationConfig' AS TableName, COUNT(*) AS RowCount FROM app.tClusterStationConfig;
IF OBJECT_ID('app.tPlanEmployeeAssignment', 'U') IS NOT NULL
    SELECT 'tPlanEmployeeAssignment' AS TableName, COUNT(*) AS RowCount FROM app.tPlanEmployeeAssignment;
IF OBJECT_ID('app.tPlanAdjustment', 'U') IS NOT NULL
    SELECT 'tPlanAdjustment' AS TableName, COUNT(*) AS RowCount FROM app.tPlanAdjustment;
IF OBJECT_ID('app.tPlanPO', 'U') IS NOT NULL
    SELECT 'tPlanPO' AS TableName, COUNT(*) AS RowCount FROM app.tPlanPO;
IF OBJECT_ID('app.tPlanMaster', 'U') IS NOT NULL
    SELECT 'tPlanMaster' AS TableName, COUNT(*) AS RowCount FROM app.tPlanMaster;
IF OBJECT_ID('app.tDemandRoot', 'U') IS NOT NULL
    SELECT 'tDemandRoot' AS TableName, COUNT(*) AS RowCount FROM app.tDemandRoot;

IF OBJECT_ID('app.tClusterStationConfig', 'U') IS NOT NULL
    DELETE FROM app.tClusterStationConfig;
IF OBJECT_ID('app.tPlanEmployeeAssignment', 'U') IS NOT NULL
    DELETE FROM app.tPlanEmployeeAssignment;
IF OBJECT_ID('app.tPlanAdjustment', 'U') IS NOT NULL
    DELETE FROM app.tPlanAdjustment;
IF OBJECT_ID('app.tPlanPO', 'U') IS NOT NULL
    DELETE FROM app.tPlanPO;
IF OBJECT_ID('app.tPlanMaster', 'U') IS NOT NULL
    DELETE FROM app.tPlanMaster;
IF OBJECT_ID('app.tDemandRoot', 'U') IS NOT NULL
    DELETE FROM app.tDemandRoot;

IF OBJECT_ID('app.tClusterStationConfig', 'U') IS NOT NULL
    SELECT 'tClusterStationConfig' AS TableName, COUNT(*) AS RowCount FROM app.tClusterStationConfig;
IF OBJECT_ID('app.tPlanEmployeeAssignment', 'U') IS NOT NULL
    SELECT 'tPlanEmployeeAssignment' AS TableName, COUNT(*) AS RowCount FROM app.tPlanEmployeeAssignment;
IF OBJECT_ID('app.tPlanAdjustment', 'U') IS NOT NULL
    SELECT 'tPlanAdjustment' AS TableName, COUNT(*) AS RowCount FROM app.tPlanAdjustment;
IF OBJECT_ID('app.tPlanPO', 'U') IS NOT NULL
    SELECT 'tPlanPO' AS TableName, COUNT(*) AS RowCount FROM app.tPlanPO;
IF OBJECT_ID('app.tPlanMaster', 'U') IS NOT NULL
    SELECT 'tPlanMaster' AS TableName, COUNT(*) AS RowCount FROM app.tPlanMaster;
IF OBJECT_ID('app.tDemandRoot', 'U') IS NOT NULL
    SELECT 'tDemandRoot' AS TableName, COUNT(*) AS RowCount FROM app.tDemandRoot;

COMMIT TRAN;
```

Neu muon kiem tra truoc khi xoa, chi chay phan `SELECT`.

Voi schema cu, thuong phan setup nhu cau me - con se nam chu yeu o:

- `app.tDemandRoot`
- `app.tPlanMaster`
- `app.tPlanPO`
- `app.tClusterStationConfig`

Con 2 bang duoc them sau nay:

- `app.tPlanAdjustment`
- `app.tPlanEmployeeAssignment`

neu chua co thi script tren se tu bo qua.

## 4. Pull code moi

Vao folder app cua tung xi nghiep:

```powershell
cd D:\Data Analyst\Tools\hanging_line_factory_XN2
git status --short
git pull origin main
```

Neu `git pull` bao local changes would be overwritten:

- commit tam local change
- hoac `git stash`
- roi pull lai

Luu y:

- `.env` la file local, giu nguyen theo tung xi nghiep
- khong copy `.env` tu repo khac sang neu server/DB khac nhau

## 5. Chay setup moi truong neu can

Neu may chua co `.venv` hoac vua clone app moi:

```powershell
.\run.ps1 -Setup
```

`-Setup` chi:

- tao `.venv`
- cai dependencies

No khong tao bang DB.

## 6. Chay migrate cau truc moi

Sau khi pull code moi, chay:

```powershell
.\run.ps1 -Migrate
```

Lenh nay se:

1. ensure `HANGING_APP_DB` ton tai
2. chay toan bo SQL migration trong `app/migrations`

Voi flow moi, migration quan trong gom:

- `009_plan_adjustments_setup_root.sql`
- `010_plan_employee_assignment.sql`

## 7. Kiem tra app dang doc dung cau hinh

Neu nghi app dang doc sai `.env`, kiem tra bang:

```powershell
.\.venv\Scripts\python.exe -c "from app import db; print(db.SERVER, db.APP_DB, db.MES_DB, db.DRIVER)"
```

Vi du ket qua dung:

```text
. hanging_app MSD2 SQL Server Native Client 11.0
```

Neu output khong khop voi `.env`, kiem tra lai:

- dung folder app dang chay chua
- file `.env` da save chua
- co bien moi truong `HANGING_*` cu dang override trong shell hay khong

## 8. Chay lai app

Sau khi migrate xong:

```powershell
.\run.ps1
```

Roi:

- login lai admin
- vao `Nhu cau me`
- nhap lai setup theo flow moi
- neu can test sync QC, chi sync tren tung `NhuCauMe`

## 9. Flow moi sau nang cap

Flow moi:

1. vao `Nhu cau me`
2. chon `MONo` goc de khai bao
3. nhap thong tin `NhuCauMe`
4. neu co bo sung so luong, dung chuc nang cap nhat SLKH
5. neu can sync nhan su sang QLCL:
   - sync theo tung `NhuCauMe`
   - chi lay dung `MONo` goc
   - chi sync cong doan co `StRole = 13`

## 10. Checklist ngan

Voi app cu da co setup:

1. backup DB app
2. xoa du lieu setup nhu cau cu
3. `git pull origin main`
4. `.\run.ps1 -Setup` neu chua co `.venv`
5. `.\run.ps1 -Migrate`
6. `.\run.ps1`
7. nhap lai setup theo flow moi
