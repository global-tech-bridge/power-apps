<#
.SYNOPSIS
    YAJ 整備キャンセル料 電子署名アプリ用の SharePoint リスト／ライブラリを作成し、
    組織マスタと同意文面マスタの初期データを投入する。

.DESCRIPTION
    data/list-schema.json を定義元として、リスト・列・インデックスを冪等に作成する。
    すでに存在するリストや列はスキップするため、何度実行しても安全。

    列は英語名で作成する。SharePoint は日本語の列名を作ると内部名が
    _x9867__x5ba2__x540d_ のようにエスケープするため、Power Automate の
    OData フィルターや Word テンプレートのマッピングが読めなくなる。

.PARAMETER SiteUrl
    対象の SharePoint サイト URL。

.PARAMETER ClientId
    PnP.PowerShell 2.x 以降で必須の Entra ID アプリ（クライアント）ID。

.PARAMETER SkipData
    リスト・列だけ作り、初期データの投入を行わない。

.EXAMPLE
    pwsh ./scripts/Provision-SharePoint.ps1 `
        -SiteUrl https://contoso.sharepoint.com/sites/yaj-cancelfee `
        -ClientId 00000000-0000-0000-0000-000000000000

.NOTES
    事前準備:
        Install-Module PnP.PowerShell -Scope CurrentUser
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SiteUrl,
    [Parameter(Mandatory)][string]$ClientId,
    [switch]$SkipData
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$schemaPath = Join-Path $repoRoot 'data/list-schema.json'
$schema = Get-Content $schemaPath -Raw -Encoding UTF8 | ConvertFrom-Json

Write-Host "接続先: $SiteUrl" -ForegroundColor Cyan
Connect-PnPOnline -Url $SiteUrl -Interactive -ClientId $ClientId

# ---------------------------------------------------------------------------
# 列の型を PnP のパラメータへ変換する
# ---------------------------------------------------------------------------
function Add-SchemaField {
    param(
        [string]$ListName,
        [psobject]$Column
    )

    $existing = Get-PnPField -List $ListName -Identity $Column.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "    - $($Column.Name) は既に存在（スキップ）" -ForegroundColor DarkGray
        return
    }

    $type = switch ($Column.Type) {
        'Text'     { 'Text' }
        'Note'     { 'Note' }
        'Number'   { 'Number' }
        'Boolean'  { 'Boolean' }
        'DateTime' { 'DateTime' }
        'Choice'   { 'Choice' }
        'User'     { 'User' }
        'URL'      { 'URL' }
        default    { throw "未対応の列型: $($Column.Type)" }
    }

    if ($type -eq 'Choice') {
        Add-PnPField -List $ListName -DisplayName $Column.Name -InternalName $Column.Name `
            -Type Choice -Choices $Column.Choices -AddToDefaultView:$false | Out-Null
    }
    else {
        Add-PnPField -List $ListName -DisplayName $Column.Name -InternalName $Column.Name `
            -Type $type -AddToDefaultView:$false | Out-Null
    }

    # 複数行テキストはプレーンテキスト・追記なしにする（同意文面の全文を素のまま保存するため）
    if ($type -eq 'Note') {
        Set-PnPField -List $ListName -Identity $Column.Name -Values @{
            RichText = $false
            AppendOnly = $false
            NumberOfLines = 12
        } | Out-Null
    }

    # 日時列は「日付と時刻」形式にする
    if ($type -eq 'DateTime') {
        Set-PnPField -List $ListName -Identity $Column.Name -Values @{
            DisplayFormat = 1   # DateTime
        } | Out-Null
    }

    if ($Column.Required -eq $true) {
        Set-PnPField -List $ListName -Identity $Column.Name -Values @{ Required = $true } | Out-Null
    }

    if ($Column.Note) {
        Set-PnPField -List $ListName -Identity $Column.Name -Values @{ Description = $Column.Note } | Out-Null
    }

    Write-Host "    + $($Column.Name) ($($Column.Type))" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# リストの作成
# ---------------------------------------------------------------------------
foreach ($name in $schema.Lists.PSObject.Properties.Name) {
    $def = $schema.Lists.$name
    Write-Host "`n[リスト] $name — $($def.Description)" -ForegroundColor Yellow

    $list = Get-PnPList -Identity $name -ErrorAction SilentlyContinue
    if (-not $list) {
        New-PnPList -Title $name -Template GenericList -OnQuickLaunch:$false | Out-Null
        Write-Host "  リストを作成しました" -ForegroundColor Green
    }
    else {
        Write-Host "  リストは既に存在" -ForegroundColor DarkGray
    }

    foreach ($col in $def.Columns) {
        Add-SchemaField -ListName $name -Column $col
    }

    # 委任可能な絞り込みと件数増加に備えたインデックス（要件定義 15.2）
    foreach ($col in ($def.Columns | Where-Object { $_.Indexed -eq $true })) {
        try {
            Set-PnPField -List $name -Identity $col.Name -Values @{ Indexed = $true } | Out-Null
            Write-Host "    * $($col.Name) にインデックスを設定" -ForegroundColor DarkCyan
        }
        catch {
            Write-Warning "    $($col.Name) のインデックス設定に失敗: $($_.Exception.Message)"
        }
    }
}

# Title 列の説明を分かりやすくする（SignatureCases では文書番号を入れる）
Set-PnPField -List 'SignatureCases' -Identity 'Title' -Values @{
    Description = '文書番号（フローが採番して設定する。ドラフト中は「（作成中）」）'
} | Out-Null
Set-PnPField -List 'DocumentNumberCounter' -Identity 'Title' -Values @{
    Description = '日付キー yyyyMMdd'
} | Out-Null

# ---------------------------------------------------------------------------
# ドキュメント ライブラリの作成
# ---------------------------------------------------------------------------
foreach ($name in $schema.Libraries.PSObject.Properties.Name) {
    $def = $schema.Libraries.$name
    Write-Host "`n[ライブラリ] $name — $($def.Description)" -ForegroundColor Yellow
    $lib = Get-PnPList -Identity $name -ErrorAction SilentlyContinue
    if (-not $lib) {
        New-PnPList -Title $name -Template DocumentLibrary -OnQuickLaunch:$false | Out-Null
        Write-Host "  ライブラリを作成しました" -ForegroundColor Green
    }
    else {
        Write-Host "  ライブラリは既に存在" -ForegroundColor DarkGray
    }
}

# 署名済みPDFは正本。バージョン管理を有効にして上書き事故に備える（要件定義 17.2）
Set-PnPList -Identity 'SignatureDocs' -EnableVersioning $true -MajorVersions 50 | Out-Null

if ($SkipData) {
    Write-Host "`n-SkipData が指定されたため初期データの投入は行いません。" -ForegroundColor Cyan
    Disconnect-PnPOnline
    return
}

# ---------------------------------------------------------------------------
# 組織マスタの投入
# ---------------------------------------------------------------------------
Write-Host "`n[初期データ] OrgMaster" -ForegroundColor Yellow
$existingOrg = (Get-PnPListItem -List 'OrgMaster' -PageSize 500).Count
if ($existingOrg -gt 0) {
    Write-Host "  既に $existingOrg 件あるため投入をスキップします（入れ直す場合はリストを空にしてから再実行）" -ForegroundColor DarkGray
}
else {
    $csvPath = Join-Path $repoRoot 'data/OrgMaster.csv'
    $rows = Import-Csv $csvPath -Encoding UTF8
    $i = 0
    foreach ($row in $rows) {
        Add-PnPListItem -List 'OrgMaster' -Values @{
            Title      = $row.Title
            BranchName = $row.BranchName
            BlockCode  = $row.BlockCode
            BlockName  = $row.BlockName
            SiteCode   = $row.SiteCode
            SiteName   = $row.SiteName
            IsActive   = ($row.IsActive -eq 'TRUE')
            SortOrder  = [int]$row.SortOrder
        } | Out-Null
        $i++
        if ($i % 20 -eq 0) { Write-Host "  $i / $($rows.Count) 件" -ForegroundColor DarkGray }
    }
    Write-Host "  $i 件を投入しました" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 同意文面マスタの投入
# ---------------------------------------------------------------------------
Write-Host "`n[初期データ] ConsentMaster" -ForegroundColor Yellow
$existingConsent = (Get-PnPListItem -List 'ConsentMaster' -PageSize 100).Count
if ($existingConsent -gt 0) {
    Write-Host "  既に $existingConsent 件あるため投入をスキップします" -ForegroundColor DarkGray
}
else {
    $bodyPath = Join-Path $repoRoot 'data/consent/ConsentText_v1.0.txt'
    $body = Get-Content $bodyPath -Raw -Encoding UTF8
    # 1行目を表示タイトル、残りを本文にする
    $lines = $body -split "`r?`n"
    $title = $lines[0].Trim()
    $text  = ($lines[1..($lines.Count - 1)] -join "`n").Trim()

    Add-PnPListItem -List 'ConsentMaster' -Values @{
        Title         = 'CANCELFEE-001'
        ConsentId     = 'CANCELFEE-001'
        Version       = '1.0'
        EffectiveFrom = (Get-Date).Date
        IsActive      = $true
        DisplayTitle  = $title
        Body          = $text
        RevisedBy     = 'サービス事業推進部（2026-06-02 起案）'
        RevisedAt     = (Get-Date)
    } | Out-Null
    Write-Host "  版 1.0 を投入しました（元資料 2026-06-02 支社起案版）" -ForegroundColor Green
    Write-Warning "  この文面は中部近畿支社サービス事業推進部の起案版です。上申・法務確認の"
    Write-Warning "  結果（収入印紙の取扱い、署名欄の過不足、保管期限）が未確定のため、"
    Write-Warning "  本番運用の開始前に docs/07-open-issues.md の残課題を確認してください。"
}

# ---------------------------------------------------------------------------
# 管理者の登録
# ---------------------------------------------------------------------------
Write-Host "`n[初期データ] AppAdmins" -ForegroundColor Yellow
$me = Get-PnPProperty -ClientObject (Get-PnPWeb) -Property CurrentUser
$existingAdmin = Get-PnPListItem -List 'AppAdmins' -PageSize 100
if ($existingAdmin.Count -gt 0) {
    Write-Host "  既に $($existingAdmin.Count) 件あるため投入をスキップします" -ForegroundColor DarkGray
}
else {
    Add-PnPListItem -List 'AppAdmins' -Values @{
        Title     = $me.Email
        UserEmail = $me.Email
        UserName  = $me.Title
        IsActive  = $true
        Note      = '構築時に自動登録'
    } | Out-Null
    Write-Host "  $($me.Email) を管理者として登録しました" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Word テンプレートのアップロード
# ---------------------------------------------------------------------------
Write-Host "`n[初期データ] DocTemplates" -ForegroundColor Yellow
$tpl = Join-Path $repoRoot 'templates/整備キャンセル料確認書.docx'
if (Test-Path $tpl) {
    Add-PnPFile -Path $tpl -Folder 'DocTemplates' | Out-Null
    Write-Host "  整備キャンセル料確認書.docx をアップロードしました" -ForegroundColor Green
}
else {
    Write-Warning "  テンプレートが見つかりません: $tpl（python3 templates/build-template.py で生成）"
}

Write-Host "`n完了しました。次は docs/01-deployment.md の「3. Power Automate フローの作成」へ。" -ForegroundColor Cyan
Disconnect-PnPOnline
