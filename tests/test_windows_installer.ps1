# Integration check in a unique temporary user root; no real desktop/startup writes.
$ErrorActionPreference = 'Stop'
$sandbox = Join-Path ([IO.Path]::GetTempPath()) ('vnc-installer-test-' + [guid]::NewGuid().ToString('N'))
$originalLocalAppData = $env:LOCALAPPDATA
$installer = Join-Path $PSScriptRoot '..\windows\install-tools.ps1'
$desktop = Join-Path $sandbox 'desktop'
$startup = Join-Path $sandbox 'startup'
try {
    $env:LOCALAPPDATA = Join-Path $sandbox 'local'
    & $installer -Action Install -DesktopDirectory $desktop -StartupDirectory $startup | Out-Null
    $installed = Join-Path $env:LOCALAPPDATA 'VncDesktopTools\app\vnc_desktop.py'
    Add-Content -LiteralPath $installed -Value '# preserved-original-marker' -Encoding UTF8
    $original = [IO.File]::ReadAllBytes($installed)
    & $installer -Action Install -DesktopDirectory $desktop -StartupDirectory $startup | Out-Null
    if ((Get-Content -LiteralPath $installed -Raw).Contains('preserved-original-marker')) { throw 'The upgrade did not replace the payload.' }
    & $installer -Action Uninstall -DesktopDirectory $desktop -StartupDirectory $startup | Out-Null
    $restored = [IO.File]::ReadAllBytes($installed)
    if ([Convert]::ToBase64String($original) -ne [Convert]::ToBase64String($restored)) { throw 'Uninstall did not restore the exact previous file.' }
    foreach ($shortcutFile in @((Join-Path $desktop 'VNC Desktop Tools.lnk'),(Join-Path $startup 'VNC Keyboard Resume.lnk'))) {
        if (-not (Test-Path -LiteralPath $shortcutFile)) { throw 'The previous shortcut was not restored.' }
    }
    Write-Output 'PASS: fresh install, upgrade backup, exact file and shortcut restoration in isolated directories.'
} finally {
    $env:LOCALAPPDATA = $originalLocalAppData
    # Keep the unique sandbox for failure diagnostics; no recursive filesystem cleanup.
}
