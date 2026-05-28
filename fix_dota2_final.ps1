# Self-elevate to admin
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")) {
    Start-Process powershell "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

Write-Host "=== Dota 2 Disk Write Fix ===" -ForegroundColor Cyan
Write-Host "Targeting D:\STEAMLIBRARY" -ForegroundColor White
Write-Host ""

$STEAM_LIB = "D:\STEAMLIBRARY"
$STEAMAPPS = "$STEAM_LIB\steamapps"
$DOTA = "$STEAMAPPS\common\dota 2 beta"

# Step 1: Kill Steam
Write-Host "[1/5] Killing Steam processes..." -ForegroundColor Yellow
$procs = @("steam", "steamwebhelper", "steamservice", "gameoverlayui")
foreach ($p in $procs) {
    Stop-Process -Name $p -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 3
Write-Host "  Done." -ForegroundColor Green

# Step 2: Remove read-only attributes
Write-Host "[2/5] Removing read-only attributes..." -ForegroundColor Yellow
attrib -R "$STEAM_LIB\*" /S /D 2>$null
attrib -R "$STEAMAPPS\*" /S /D 2>$null
if (Test-Path $DOTA) {
    attrib -R "$DOTA\*" /S /D 2>$null
    Write-Host "  Cleared attributes on Dota folder." -ForegroundColor Green
} else {
    Write-Host "  WARNING: Dota folder not found at $DOTA" -ForegroundColor Red
    $DOTA2 = "$STEAMAPPS\common\Dota 2"
    if (Test-Path $DOTA2) {
        attrib -R "$DOTA2\*" /S /D 2>$null
        Write-Host "  Found and cleared: $DOTA2" -ForegroundColor Green
    }
}

# Step 3: Fix NTFS permissions
Write-Host "[3/5] Fixing folder permissions..." -ForegroundColor Yellow
$username = $env:USERNAME
icacls $STEAM_LIB /grant "${username}:(OI)(CI)F" /T /C /Q 2>$null
Write-Host "  Fixed: $STEAM_LIB" -ForegroundColor Green
icacls $STEAMAPPS /grant "${username}:(OI)(CI)F" /C /Q 2>$null
Write-Host "  Fixed: $STEAMAPPS" -ForegroundColor Green

# Step 4: Delete download cache
Write-Host "[4/5] Clearing Steam download cache..." -ForegroundColor Yellow
$to_delete = @("$STEAMAPPS\downloading", "$STEAMAPPS\temp")
foreach ($path in $to_delete) {
    if (Test-Path $path) {
        Remove-Item $path -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  Deleted: $path" -ForegroundColor Green
    } else {
        Write-Host "  Already clean: $path" -ForegroundColor Gray
    }
}

# Step 5: Relaunch Steam
Write-Host "[5/5] Restarting Steam..." -ForegroundColor Yellow
$steam_exe = $null
$steam_paths = @(
    "C:\Program Files (x86)\Steam\steam.exe",
    "C:\Program Files\Steam\steam.exe"
)
foreach ($p in $steam_paths) {
    if (Test-Path $p) { $steam_exe = $p; break }
}
if (-not $steam_exe) {
    try {
        $reg = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Valve\Steam" -ErrorAction SilentlyContinue
        if ($reg -and (Test-Path "$($reg.InstallPath)\steam.exe")) {
            $steam_exe = "$($reg.InstallPath)\steam.exe"
        }
    } catch {}
}
if ($steam_exe) {
    Start-Process $steam_exe
    Write-Host "  Steam launched from: $steam_exe" -ForegroundColor Green
} else {
    Write-Host "  Could not find steam.exe - open Steam manually." -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host ""
Write-Host "After Steam opens:" -ForegroundColor White
Write-Host "  Right-click Dota 2 > Properties > Local Files > Verify integrity of game files" -ForegroundColor White
Write-Host ""
Read-Host "Press Enter to close"
