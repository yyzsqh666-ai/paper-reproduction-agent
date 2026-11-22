param(
    [Parameter(Mandatory)][ValidateSet('smoke', 'full')][string]$Mode,
    [string]$PythonExecutable = 'python'
)
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$started = [DateTimeOffset]::UtcNow
$runId = $started.ToString('yyyyMMddTHHmmss.fffffffZ') + '-' + $Mode + '-' + [guid]::NewGuid().ToString('N')
$output = Join-Path (Join-Path $PSScriptRoot 'evidence') $runId
New-Item -ItemType Directory -Path $output -ErrorAction Stop | Out-Null
$childArgs = @('-B', '-u', './run.py', '--mode', $Mode, '--output', $output, '--reserved')
$launcher = [ordered]@{
    executable = (Get-Process -Id $PID).Path
    argv = [Environment]::GetCommandLineArgs()
    cwd = (Get-Location).Path
    powershell_version = $PSVersionTable.PSVersion.ToString()
    ancestor_argv = $null
    start_utc = $started.ToString('o')
    stdout = 'inherited'
    stderr = 'inherited'
}
$child = [ordered]@{executable=$PythonExecutable; argv=@($PythonExecutable)+$childArgs
    cwd=$PSScriptRoot; start_utc=$null; end_utc=$null; exit_code=$null
    stdout='stdout.txt'; stderr='stderr.txt'}
$code = 1
$errorText = $null
$stdout = ''
$stderr = ''
try {
    $exe = (Get-Command $PythonExecutable -CommandType Application -ErrorAction Stop).Source
    $child.executable = $exe
    $child.argv = @($exe) + $childArgs
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $exe
    # Only the generated absolute output path may contain spaces.
    $info.Arguments = '-B -u ./run.py --mode ' + $Mode + ' --output "' + $output + '" --reserved'
    $info.WorkingDirectory = $PSScriptRoot
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = $utf8
    $info.StandardErrorEncoding = $utf8
    foreach ($key in @('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')) {
        $info.EnvironmentVariables[$key] = '1'
    }
    $info.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
    $info.EnvironmentVariables['MPLBACKEND'] = 'Agg'
    $info.EnvironmentVariables['MPLCONFIGDIR'] = Join-Path $output '.mpl-cache'
    $child.start_utc = [DateTimeOffset]::UtcNow.ToString('o')
    $process = [Diagnostics.Process]::Start($info)
    $readOut = $process.StandardOutput.ReadToEndAsync()
    $readErr = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $child.end_utc = [DateTimeOffset]::UtcNow.ToString('o')
    $child.exit_code = $process.ExitCode
    $code = $process.ExitCode
    $stdout = $readOut.Result
    $stderr = $readErr.Result
    $process.Dispose()
} catch {
    $errorText = $_.Exception.Message
    $stderr += $errorText
    $code = 1
}
[IO.Directory]::CreateDirectory($output) | Out-Null
[IO.File]::WriteAllText((Join-Path $output 'stdout.txt'), $stdout, $utf8)
[IO.File]::WriteAllText((Join-Path $output 'stderr.txt'), $stderr, $utf8)
[IO.File]::WriteAllText((Join-Path $output 'run-log.txt'), ($stdout + $stderr + " Exit status: $code"), $utf8)
$launcher.end_utc = [DateTimeOffset]::UtcNow.ToString('o')
$launcher.exit_code = $code
$result = [ordered]@{launcher=$launcher; child=$child; error=$errorText; success=($code -eq 0)}
[IO.File]::WriteAllText((Join-Path $output 'launcher.json'), ($result | ConvertTo-Json -Depth 6), $utf8)
[Console]::WriteLine($stdout)
[Console]::Error.WriteLine($stderr)
exit $code
