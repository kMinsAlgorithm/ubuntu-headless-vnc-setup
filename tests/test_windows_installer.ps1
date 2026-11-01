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
    foreach ($shortcutFile in @((Join-Path $desktop 'VNC Desktop Tools.lnk'),(Join-Path $startup 'VNC Keyboard Resume.lnk'),(Join-Path $startup 'VNC Session Resume.lnk'))) {
        if (-not (Test-Path -LiteralPath $shortcutFile)) { throw 'The previous shortcut was not restored.' }
    }
    $env:LOCALAPPDATA = Join-Path $sandbox 'keyboard-only-local'
    $keyboardDesktop = Join-Path $sandbox 'keyboard-only-desktop'
    $keyboardStartup = Join-Path $sandbox 'keyboard-only-startup'
    & $installer -Action Install -DesktopDirectory $keyboardDesktop -StartupDirectory $keyboardStartup | Out-Null
    $keyboardFile = Join-Path $env:LOCALAPPDATA 'VncDesktopTools\app\keyboard_hook.py'
    Add-Content -LiteralPath $keyboardFile -Value '# previous-keyboard-version' -Encoding UTF8
    $state = Join-Path $env:LOCALAPPDATA 'VncDesktopTools\state'
    New-Item -ItemType Directory -Path $state -Force | Out-Null
    $noBom = New-Object Text.UTF8Encoding $false
    [IO.File]::WriteAllText((Join-Path $state 'session-preference.json'), (@{enabled=$true;profile='mac';port=5900} | ConvertTo-Json), $noBom)
    [IO.File]::WriteAllText((Join-Path $state 'session-runtime.json'), (@{running=$true;pid=0;token='isolated-test';phase='virtual';heartbeat=([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000)} | ConvertTo-Json), $noBom)
    & $installer -Action Install -DesktopDirectory $keyboardDesktop -StartupDirectory $keyboardStartup | Out-Null
    if (Test-Path -LiteralPath (Join-Path $state 'session-stop.json')) { throw 'Keyboard-only update stopped automatic display mode.' }
    if (-not (Get-Content -LiteralPath (Join-Path $state 'session-preference.json') -Raw | ConvertFrom-Json).enabled) { throw 'Keyboard-only update changed the automatic display preference.' }
    Write-Output 'PASS: fresh install, upgrade backup, exact restoration, and keyboard-only update preserves automatic display mode.'
} finally {
    $env:LOCALAPPDATA = $originalLocalAppData
    # Keep the unique sandbox for failure diagnostics; no recursive filesystem cleanup.
}
