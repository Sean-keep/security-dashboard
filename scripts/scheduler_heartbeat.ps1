$ErrorActionPreference = "SilentlyContinue"
try {
    $resp = Invoke-RestMethod "http://localhost:5000/api/scheduler/status" -TimeoutSec 5
    if ($resp.running) {
        Write-Output "[OK] Scheduler running, $($resp.jobs.Count) jobs"
    } else {
        Write-Output "[WARN] Scheduler not running"
    }
} catch {
    Write-Output "[ERROR] $_"
}
