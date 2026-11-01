# Windows PowerShell 5.1+, Windows x64. No passwords are written to receipts.
[CmdletBinding()]
param(
    [ValidateSet('Check', 'InstallVnc', 'InstallVirtualDisplay', 'RemoveVirtualDisplay')]
    [string]$Action = 'Check',
    [ValidateRange(1,65535)][int]$Port = 5900,
    [Security.SecureString]$VncPassword,
    [Security.SecureString]$ControlPassword,
    [string[]]$RemoteAddress = @('Any')
)
$ErrorActionPreference = 'Stop'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'packages.json') -Raw | ConvertFrom-Json
$dataFolder = Join-Path $env:ProgramData 'VncDesktopTools'

function Get-VirtualDevices {
    @(Get-PnpDevice -Class Display -PresentOnly -ErrorAction SilentlyContinue | Where-Object {
        $ids = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_HardwareIds' -ErrorAction SilentlyContinue).Data
        @($ids) -contains 'Root\MttVDD'
    })
}

function Get-VncStatus {
    $service = Get-CimInstance Win32_Service -Filter "Name='tvnserver'"
    $settings = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\TightVNC\Server' -Name RfbPort,UseVncAuthentication,AcceptHttpConnections -ErrorAction SilentlyContinue
    [ordered]@{
        Installed = ($null -ne $service)
        ServiceStatus = $service.State
        StartMode = $service.StartMode
        Port = $settings.RfbPort
        ConfigurationAccess = $(if ($null -ne $settings) {'readable'} else {'administrator-required-or-unavailable'})
        AuthenticationRequired = $(if ($null -ne $settings) {$settings.UseVncAuthentication -eq 1} else {$null})
        HttpEnabled = $(if ($null -ne $settings) {$settings.AcceptHttpConnections -eq 1} else {$null})
        VirtualDisplay = @(Get-VirtualDevices | Select-Object FriendlyName, Status)
    }
}

function Get-VerifiedPackage([string]$Name) {
    $package = $manifest.$Name
    $cache = Join-Path $dataFolder 'packages'
    New-Item -ItemType Directory -Path $cache -Force | Out-Null
    $destination = Join-Path $cache ([IO.Path]::GetFileName(([uri]$package.url).AbsolutePath))
    if (-not (Test-Path -LiteralPath $destination)) {
        $temporary = $destination + '.download'
        try {
            Invoke-WebRequest -Uri $package.url -OutFile $temporary -UseBasicParsing
            if ((Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash -ne $package.sha256) { throw "Package hash mismatch: $Name" }
            Move-Item -LiteralPath $temporary -Destination $destination
        } finally {
            if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
        }
    }
    if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne $package.sha256) { throw "Cached package hash mismatch: $Name" }
    return $destination
}

function Assert-Signature([string]$Path, [string]$Publisher) {
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch [regex]::Escape($Publisher)) {
        throw "Signature validation failed: $Path"
    }
}

function Get-PlainPassword([Security.SecureString]$Secret) {
    $value = [PSCredential]::new('VNC', $Secret).GetNetworkCredential().Password
    if ($value.Length -ne 8 -or $value -cnotmatch '^[A-Za-z0-9!#%+,_=-]{8}$') {
        throw 'Use exactly 8 ASCII letters, numbers, or !#%+,_=- for legacy VNC authentication.'
    }
    return $value
}

if ($Action -eq 'Check') { Get-VncStatus | ConvertTo-Json -Depth 5; return }
if (-not [Environment]::Is64BitProcess -or -not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
    throw 'Run 64-bit Windows PowerShell on Windows x64. ARM64 packages are not supported by this installer.'
}
if (-not [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Open PowerShell as Administrator, then run the prepared command again.'
}

if ($Action -eq 'InstallVnc') {
    $existing = Get-VncStatus
    if ($existing.Installed) {
        if (-not $existing.AuthenticationRequired) { throw 'Existing server has authentication disabled; configure it before proceeding.' }
        # Preserve working server configuration and credentials, including a non-default port.
        $existing | ConvertTo-Json -Depth 5
        return
    }
    $installer = Get-VerifiedPackage 'tightvnc'
    Assert-Signature $installer $manifest.tightvnc.signer
    if (-not $VncPassword) { $VncPassword = Read-Host 'VNC password (8 ASCII characters)' -AsSecureString }
    if (-not $ControlPassword) { $ControlPassword = Read-Host 'Settings password (8 ASCII characters)' -AsSecureString }
    $plainVnc = Get-PlainPassword $VncPassword
    $plainControl = Get-PlainPassword $ControlPassword
    $arguments = @('/i', ('"' + $installer + '"'), '/qn', '/norestart', 'ADDLOCAL=Server',
        'SERVER_REGISTER_AS_SERVICE=1', 'SERVER_ADD_FIREWALL_EXCEPTION=0',
        'SET_ACCEPTRFBCONNECTIONS=1', 'VALUE_OF_ACCEPTRFBCONNECTIONS=0',
        'SET_ACCEPTHTTPCONNECTIONS=1', 'VALUE_OF_ACCEPTHTTPCONNECTIONS=0',
        'SET_USEVNCAUTHENTICATION=1', 'VALUE_OF_USEVNCAUTHENTICATION=1',
        'SET_PASSWORD=1', ('VALUE_OF_PASSWORD=' + $plainVnc),
        'SET_USECONTROLAUTHENTICATION=1', 'VALUE_OF_USECONTROLAUTHENTICATION=1',
        'SET_CONTROLPASSWORD=1', ('VALUE_OF_CONTROLPASSWORD=' + $plainControl),
        'SET_ALLOWLOOPBACK=1', 'VALUE_OF_ALLOWLOOPBACK=1',
        'SET_RFBPORT=1', ('VALUE_OF_RFBPORT=' + $Port),
        'MsiHiddenProperties="VALUE_OF_PASSWORD;VALUE_OF_CONTROLPASSWORD"')
    try {
        $process = Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
        if ($process.ExitCode -notin 0,3010) { throw "MSI installation failed: $($process.ExitCode)" }
    } finally { $plainVnc = $null; $plainControl = $null; $arguments = $null }
    $settingsPath = 'HKLM:\SOFTWARE\TightVNC\Server'
    $settings = Get-ItemProperty -LiteralPath $settingsPath
    if ($settings.UseVncAuthentication -ne 1 -or -not $settings.Password -or $settings.Password.Length -ne 8) {
        throw 'Password configuration failed; inbound access remains disabled.'
    }
    New-NetFirewallRule -Name 'VncDesktopTools-TightVNC' -DisplayName 'VNC Desktop Tools - TightVNC' -Direction Inbound -Action Allow -Profile Any -Protocol TCP -LocalPort $Port -RemoteAddress $RemoteAddress -Program "$env:ProgramFiles\TightVNC\tvnserver.exe" | Out-Null
    Set-ItemProperty -LiteralPath $settingsPath -Name AcceptRfbConnections -Type DWord -Value 1
    Set-Service -Name tvnserver -StartupType Automatic
    Restart-Service -Name tvnserver
    Get-VncStatus | ConvertTo-Json -Depth 5
    return
}

if ($Action -eq 'InstallVirtualDisplay') {
    $existingDevices = Get-VirtualDevices
    if ($existingDevices.Count -gt 0) {
        [ordered]@{ Status='existing-preserved'; Devices=@($existingDevices | Select-Object FriendlyName,Status) } | ConvertTo-Json -Depth 4
        return
    }
    $driverZip = Get-VerifiedPackage 'virtual_display'
    $nefconZip = Get-VerifiedPackage 'nefcon'
    $driverFolder = Join-Path $dataFolder 'driver-25.7.23'
    $nefconFolder = Join-Path $dataFolder 'nefcon-1.14.0'
    Expand-Archive -LiteralPath $driverZip -DestinationPath $driverFolder -Force
    Expand-Archive -LiteralPath $nefconZip -DestinationPath $nefconFolder -Force
    $inf = Join-Path $driverFolder 'VirtualDisplayDriver\MttVDD.inf'
    $catalog = Join-Path $driverFolder 'VirtualDisplayDriver\mttvdd.cat'
    $nefcon = Join-Path $nefconFolder 'x64\nefconw.exe'
    Assert-Signature $catalog $manifest.virtual_display.signer
    Assert-Signature $nefcon $manifest.nefcon.signer
    $backup = Join-Path $dataFolder ('backups\' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmss.fffffffZ'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    $settingsFolder = Join-Path $env:SystemDrive 'VirtualDisplayDriver'
    $settingsFile = Join-Path $settingsFolder 'vdd_settings.xml'
    $settingsExisted = Test-Path -LiteralPath $settingsFile
    if ($settingsExisted) { Copy-Item -LiteralPath $settingsFile -Destination (Join-Path $backup 'vdd_settings.xml') }
    New-Item -ItemType Directory -Path $settingsFolder -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'vdd_settings.xml') -Destination $settingsFile -Force
    $receipt = [ordered]@{ Action='InstallVirtualDisplay'; SettingsFile=$settingsFile; SettingsExisted=$settingsExisted; Backup=$backup; Status='prepared' }
    $receiptPath = Join-Path $backup 'receipt.json'
    $receipt | ConvertTo-Json | Set-Content -LiteralPath $receiptPath -Encoding UTF8
    $result = Start-Process -FilePath $nefcon -ArgumentList @('install', ('"' + $inf + '"'), 'Root\MttVDD') -Wait -PassThru -WindowStyle Hidden
    if ($result.ExitCode -notin 0,3010) {
        if ($settingsExisted) { Copy-Item -LiteralPath (Join-Path $backup 'vdd_settings.xml') -Destination $settingsFile -Force }
        else { Remove-Item -LiteralPath $settingsFile }
        throw "Virtual driver installation failed ($($result.ExitCode)); inspect Device Manager and backup $backup"
    }
    $devices = @()
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        $devices = Get-VirtualDevices
        if (@($devices | Where-Object Status -eq 'OK').Count -gt 0) { break }
        Start-Sleep -Milliseconds 500
    }
    $receipt.Status = 'installed'
    $receipt['Devices'] = @($devices | Select-Object InstanceId,FriendlyName,Status)
    $receipt['SettingsSHA256'] = (Get-FileHash -LiteralPath $settingsFile -Algorithm SHA256).Hash
    $receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
    Copy-Item -LiteralPath $receiptPath -Destination (Join-Path $dataFolder 'virtual-display-receipt.json') -Force
    if (@($devices | Where-Object Status -eq 'OK').Count -eq 0) { throw "Driver installed but no healthy display was found. Inspect Device Manager; receipt: $receiptPath" }
    [ordered]@{ Status='installed'; Devices=@($devices | Select-Object FriendlyName,Status); Receipt=$receiptPath; RebootRequired=($result.ExitCode -eq 3010) } | ConvertTo-Json -Depth 5
    return
}

if ($Action -eq 'RemoveVirtualDisplay') {
    $receiptPath = Join-Path $dataFolder 'virtual-display-receipt.json'
    if (-not (Test-Path -LiteralPath $receiptPath)) { throw 'No installer receipt exists. Use Device Manager for an independently installed driver.' }
    $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    foreach ($device in $receipt.Devices) {
        & "$env:SystemRoot\System32\pnputil.exe" /remove-device $device.InstanceId
        if ($LASTEXITCODE -ne 0) { throw "Could not remove $($device.InstanceId)" }
    }
    if ((Test-Path -LiteralPath $receipt.SettingsFile) -and (Get-FileHash -LiteralPath $receipt.SettingsFile -Algorithm SHA256).Hash -eq $receipt.SettingsSHA256) {
        if ($receipt.SettingsExisted) { Copy-Item -LiteralPath (Join-Path $receipt.Backup 'vdd_settings.xml') -Destination $receipt.SettingsFile -Force }
        else { Remove-Item -LiteralPath $receipt.SettingsFile }
    }
    [ordered]@{ Status='removed'; Backup=$receipt.Backup; DriverStorePackage='preserved' } | ConvertTo-Json
}
