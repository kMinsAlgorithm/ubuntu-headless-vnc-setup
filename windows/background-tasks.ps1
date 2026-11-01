[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('Install','Restore','Start','Check')][string]$Action,
    [Parameter(Mandatory=$true)][string]$AppDirectory,
    [string]$PythonWindowless,
    [string]$BackupDirectory,
    [ValidateSet('keyboard','session')][string]$Kind
)
$ErrorActionPreference = 'Stop'
$app = [IO.Path]::GetFullPath($AppDirectory).TrimEnd('\')
$script = Join-Path $app 'vnc_desktop.py'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$sha = [Security.Cryptography.SHA256]::Create()
try { $identity = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($sid+'|'+$app.ToLowerInvariant())))).Replace('-','').Substring(0,20) }
finally { $sha.Dispose() }
$description = 'VncDesktopTools user background workers '+$identity
$scheduler = New-Object -ComObject Schedule.Service
$scheduler.Connect()
$folder = $scheduler.GetFolder('\')
function Task-Name([string]$worker) { return 'VncDesktopTools-'+$identity+'-'+$worker }
function Existing-Task([string]$name) {
    try { return $folder.GetTask($name) }
    catch { if ($_.Exception.HResult -eq -2147024894) { return $null }; throw }
}
function Assert-Owned($task) {
    if ($task -and $task.Definition.RegistrationInfo.Description -ne $description) { throw 'Refusing to change an unrelated scheduled task.' }
}
if ($Action -eq 'Start') {
    if (-not $Kind) { throw 'A worker kind is required.' }
    $task = Existing-Task (Task-Name $Kind)
    if (-not $task) { throw 'The user background task is not installed.' }
    Assert-Owned $task
    $entry = $task.Definition.Actions.Item(1)
    if ($entry.Arguments -ne ('"'+$script+'" _background '+$Kind) -or $entry.WorkingDirectory -ne $app -or $task.Definition.Principal.RunLevel -ne 0 -or $task.Definition.Principal.LogonType -ne 3) { throw 'The scheduled task does not match this user installation.' }
    $null = $task.Run($null)
    return
}
if ($Action -eq 'Check') {
    foreach ($worker in @('keyboard','session')) {
        $task = Existing-Task (Task-Name $worker)
        Assert-Owned $task
        [pscustomobject]@{Kind=$worker;Installed=[bool]$task;State=$(if ($task) {$task.State} else {$null})}
    }
    return
}
if (-not $BackupDirectory) { throw 'A private installation backup directory is required.' }
$receiptPath = Join-Path $BackupDirectory 'background-tasks.json'
$noBom = New-Object Text.UTF8Encoding $false
if ($Action -eq 'Restore') {
    if (-not (Test-Path -LiteralPath $receiptPath)) { return }
    $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($previous in $receipt) {
        if ($previous.Kind -notin @('keyboard','session') -or $previous.Name -ne (Task-Name $previous.Kind)) { throw 'Unexpected scheduled task in the installation receipt.' }
        $task = Existing-Task $previous.Name
        Assert-Owned $task
        if ($previous.Existed) {
            $xml = [IO.File]::ReadAllText((Join-Path $BackupDirectory ($previous.Kind+'-task.xml')))
            $null = $folder.RegisterTask($previous.Name,$xml,6,$sid,$null,3)
        } elseif ($task) { $folder.DeleteTask($previous.Name,0) }
    }
    return
}
if (-not (Test-Path -LiteralPath $PythonWindowless) -or -not (Test-Path -LiteralPath $script)) { throw 'The installed Python and tool must exist before registering tasks.' }
$receipt = @()
foreach ($worker in @('keyboard','session')) {
    $name = Task-Name $worker
    $previous = Existing-Task $name
    Assert-Owned $previous
    if ($previous) { [IO.File]::WriteAllText((Join-Path $BackupDirectory ($worker+'-task.xml')),$previous.Xml,$noBom) }
    $receipt += [pscustomobject]@{Kind=$worker;Name=$name;Existed=[bool]$previous}
    [IO.File]::WriteAllText($receiptPath,(ConvertTo-Json -InputObject @($receipt)),$noBom)
    $definition = $scheduler.NewTask(0)
    $definition.RegistrationInfo.Description = $description
    $definition.Principal.UserId = $sid
    $definition.Principal.LogonType = 3
    $definition.Principal.RunLevel = 0
    $definition.Settings.ExecutionTimeLimit = 'PT0S'
    $definition.Settings.DisallowStartIfOnBatteries = $false
    $definition.Settings.StopIfGoingOnBatteries = $false
    $definition.Settings.MultipleInstances = 2
    $trigger = $definition.Triggers.Create(9)
    $trigger.UserId = $sid
    $trigger.Delay = 'PT5S'
    $entry = $definition.Actions.Create(0)
    $entry.Path = $PythonWindowless
    $entry.Arguments = '"'+$script+'" _background '+$worker
    $entry.WorkingDirectory = $app
    $null = $folder.RegisterTaskDefinition($name,$definition,6,$sid,$null,3)
}
