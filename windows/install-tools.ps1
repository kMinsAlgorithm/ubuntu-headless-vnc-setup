[CmdletBinding()]
param(
    [ValidateSet('Check','Install','Uninstall')][string]$Action='Check',
    [string]$PythonPath = 'python',
    [string]$DesktopDirectory = [Environment]::GetFolderPath('Desktop'),
    [string]$StartupDirectory = [Environment]::GetFolderPath('Startup')
)
$ErrorActionPreference = 'Stop'
$appRoot = Join-Path $env:LOCALAPPDATA 'VncDesktopTools'
$python = (Get-Command $PythonPath -ErrorAction Stop).Source
& $python -c 'import sys, tkinter; assert sys.version_info >= (3, 9), "Python 3.9+ is required"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.9+ with tkinter is required.' }
if ($Action -eq 'Install') { New-Item -ItemType Directory -Path $appRoot -Force | Out-Null }
# Resolve existing handles through AppData virtualization before giving paths to
# Task Scheduler, which runs outside the installer application's process tree.
$encodedRoot = & $python -c "import base64,sys; sys.path.insert(0,sys.argv[1]); from app_paths import physical_path; print(base64.b64encode(str(physical_path(sys.argv[2])).encode('utf-8')).decode('ascii'))" $PSScriptRoot $appRoot
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the user installation directory.' }
$appRoot = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encodedRoot))
$app = Join-Path $appRoot 'app'
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'pythonw.exe was not found next to the selected Python interpreter.' }
$desktop = $DesktopDirectory
$startup = $StartupDirectory
$guiShortcut = Join-Path $desktop 'VNC Desktop Tools.lnk'
$startupShortcut = Join-Path $startup 'VNC Keyboard Resume.lnk'
$sessionShortcut = Join-Path $startup 'VNC Session Resume.lnk'
$files = @('vnc_desktop.py','win32_backend.py','keyboard_hook.py','ime_bridge.py','session_mode.py','session_observer.py','app_paths.py','background.py','background-tasks.ps1')
$targets = @($files | ForEach-Object { Join-Path $app $_ }) + @($guiShortcut,$startupShortcut,$sessionShortcut)
if ($Action -eq 'Check') {
    [ordered]@{
        Python=$python; PythonWindowless=$pythonw; Desktop=$desktop; AppDirectory=$app
        Sources=@($files | ForEach-Object { $source = Join-Path $PSScriptRoot $_; if (-not (Test-Path -LiteralPath $source)) { throw "Missing source: $_" }; @{Name=$_;SHA256=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash} })
    } | ConvertTo-Json -Depth 4
    return
}
$installedScript = Join-Path $app 'vnc_desktop.py'
$sourceScript = Join-Path $PSScriptRoot 'vnc_desktop.py'
$displayPayloadChanged = $false
foreach ($file in @('vnc_desktop.py','win32_backend.py','session_mode.py','session_observer.py','app_paths.py','background.py','background-tasks.ps1')) {
    $destination = Join-Path $app $file
    if (-not (Test-Path -LiteralPath $destination) -or (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $file) -Algorithm SHA256).Hash) {
        $displayPayloadChanged = $true
    }
}
$automaticWasRunning = $false
$automaticNeedsResume = $false
$automaticProfile = 'mac'
if (Test-Path -LiteralPath (Join-Path $app 'session_mode.py')) {
    $automaticState = (& $python $sourceScript auto status | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect automatic display mode.' }
    $automaticWasRunning = $automaticState.running -or $automaticState.worker_active
    $automaticProfile = $automaticState.profile
    if (($automaticWasRunning -and $displayPayloadChanged) -or $Action -eq 'Uninstall') {
        & $python $sourceScript auto off | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Restore the automatic display session before changing installed files.' }
        $automaticNeedsResume = $automaticWasRunning
    }
}
$operationLock = Join-Path $appRoot 'state\display-operation.lock'
if ($displayPayloadChanged -and (Test-Path -LiteralPath $operationLock)) {
    $lockCheck = [IO.File]::Open($operationLock, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $lockCheck.Dispose()
}
$keyboardWasRunning = $false
$commandAsControl = $false
if (Test-Path -LiteralPath $installedScript) {
    $keyboardState = (& $python $installedScript keyboard status | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the existing keyboard mode.' }
    $keyboardWasRunning = $keyboardState.running
    $commandAsControl = $keyboardState.command_as_control
    if ($keyboardWasRunning -or $Action -eq 'Uninstall') {
        & $python $installedScript keyboard off | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Stop the existing keyboard mode before changing installed files.' }
    }
}
$receiptPath = Join-Path $appRoot 'install-receipt.json'
if ($Action -eq 'Uninstall') {
    $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    & (Join-Path $PSScriptRoot 'background-tasks.ps1') -Action Restore -AppDirectory $app -BackupDirectory $receipt.Backup
    foreach ($file in $receipt.Files) {
        if ($file.Destination -notin $targets) { throw 'Receipt contains an unexpected destination.' }
        if ($file.Existed) { Copy-Item -LiteralPath $file.Backup -Destination $file.Destination -Force }
        elseif (Test-Path -LiteralPath $file.Destination) { Remove-Item -LiteralPath $file.Destination }
    }
    [ordered]@{ Status='restored-before-last-install'; StatePreserved=(Join-Path $appRoot 'state'); Backup=$receipt.Backup } | ConvertTo-Json
    return
}
$backup = Join-Path $appRoot ('install-backups\' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmss.fffffffZ'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$receipt = [ordered]@{Status='prepared'; Backup=$backup; Files=@(); Python=$python}
foreach ($target in $targets) {
    $existed = Test-Path -LiteralPath $target
    if ($existed -and (Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing to replace a link: $target" }
    $previous = Join-Path $backup ([IO.Path]::GetFileName($target))
    if ($existed) { Copy-Item -LiteralPath $target -Destination $previous }
    $receipt.Files += @{Destination=$target;Existed=$existed;Backup=$(if ($existed) {$previous} else {$null})}
}
$backupReceipt = Join-Path $backup 'receipt.json'
$receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $backupReceipt -Encoding UTF8
try {
    New-Item -ItemType Directory -Path $app -Force | Out-Null
    foreach ($file in $files) {
        $destination = Join-Path $app $file
        $source = Join-Path $PSScriptRoot $file
        if (-not (Test-Path -LiteralPath $destination) -or (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash) {
            Copy-Item -LiteralPath $source -Destination $destination -Force
        }
    }
    & (Join-Path $PSScriptRoot 'background-tasks.ps1') -Action Install -AppDirectory $app -PythonWindowless $pythonw -BackupDirectory $backup
    $shell = New-Object -ComObject WScript.Shell
    New-Item -ItemType Directory -Path $desktop,$startup -Force | Out-Null
    foreach ($entry in @(@($guiShortcut,'gui'), @($startupShortcut,'resume-keyboard'), @($sessionShortcut,'resume-session'))) {
        $shortcut = $shell.CreateShortcut($entry[0])
        $shortcut.TargetPath = $pythonw
        $shortcut.Arguments = '"' + $installedScript + '" ' + $entry[1]
        $shortcut.WorkingDirectory = $app
        $shortcut.Description = 'Windows VNC display and keyboard tools'
        $shortcut.Save()
    }
    $receipt.Status = 'installed'
    $receipt['SHA256'] = @($files | ForEach-Object { @{Name=$_;Hash=(Get-FileHash -LiteralPath (Join-Path $app $_) -Algorithm SHA256).Hash} })
    $receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $backupReceipt -Encoding UTF8
    Copy-Item -LiteralPath $backupReceipt -Destination $receiptPath -Force
} catch {
    try { & (Join-Path $PSScriptRoot 'background-tasks.ps1') -Action Restore -AppDirectory $app -BackupDirectory $backup }
    catch { Write-Warning 'Scheduled task rollback needs attention; the private task backup was preserved.' }
    foreach ($file in $receipt.Files) {
        if ($file.Existed) { Copy-Item -LiteralPath $file.Backup -Destination $file.Destination -Force }
        elseif (Test-Path -LiteralPath $file.Destination) { Remove-Item -LiteralPath $file.Destination }
    }
    throw
} finally {
    if ($automaticNeedsResume) {
        & $python $installedScript auto on --profile $automaticProfile | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Files were installed/restored but automatic display mode needs attention.' }
    }
    if ($keyboardWasRunning) {
        $resumeArguments = @($installedScript,'keyboard','on')
        if ($commandAsControl) { $resumeArguments += '--command-as-control' }
        & $python @resumeArguments | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Files were installed/restored but the previous keyboard mode needs attention.' }
    }
}
$receipt | ConvertTo-Json -Depth 5
