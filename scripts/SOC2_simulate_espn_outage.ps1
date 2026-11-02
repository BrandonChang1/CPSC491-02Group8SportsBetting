# ESPN API Outage Simulation
# Run PowerShell as Administrator.

$domains = @(
    "site.api.espn.com",
    "site.web.api.espn.com",
    "cdn.espn.com",
    "now.core.api.espn.com"
)

$hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$backupPath = Join-Path $env:TEMP (
    "espn-hosts-backup-" + [guid]::NewGuid().ToString() + ".bak"
)

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)

if (-not $principal.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)) {
    Write-Host "ERROR: Run PowerShell as Administrator." -ForegroundColor Red
    exit 1
}

function Test-EspnDomains {
    param([string]$Phase)

    Write-Host "`n=== $Phase ===" -ForegroundColor Cyan

    foreach ($domain in $domains) {
        Write-Host "`nTesting $domain" -ForegroundColor Yellow

        # Check HTTPS TCP connectivity (the API may not respond to ICMP ping).
        $tcpConnected = Test-NetConnection -ComputerName $domain -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue
        Write-Host "TCP port 443 reachable: $tcpConnected"

        # Verify hostname resolution independently; localhost may accept TCP connections.
        try {
            $addresses = [System.Net.Dns]::GetHostAddresses($domain)
            $ips = @($addresses | ForEach-Object { $_.ToString() })
            Write-Host "Resolved IPs: $($ips -join ', ')"

            $allBlocked = @(
                $ips | Where-Object {
                    $_ -ne "127.0.0.1" -and $_ -ne "::1"
                }
            ).Count -eq 0 -and $ips.Count -gt 0

            if ($Phase -eq "AFTER BLOCKING") {
                if ($allBlocked) {
                    Write-Host "BLOCKED: $domain" -ForegroundColor Green
                } else {
                    Write-Host "WARNING: Domain may still be accessible!" -ForegroundColor Red
                }
            }
        }
        catch {
            Write-Host "DNS resolution failed: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

$backupCreated = $false

try {
    # STEP 1: Check connectivity before blocking.
    Test-EspnDomains "BEFORE BLOCKING"

    # STEP 2: Back up original hosts file.
    Copy-Item -LiteralPath $hostsPath -Destination $backupPath -ErrorAction Stop
    $backupCreated = $true

    # STEP 3: Block ESPN API domains.
    Write-Host "`nBlocking ESPN API domains..." -ForegroundColor Cyan
    Add-Content -LiteralPath $hostsPath -Value "`r`n# ESPN OUTAGE TEST START" -ErrorAction Stop

    foreach ($domain in $domains) {
        Add-Content -LiteralPath $hostsPath -Value "127.0.0.1 $domain" -ErrorAction Stop
        Add-Content -LiteralPath $hostsPath -Value "::1 $domain" -ErrorAction Stop
    }

    Add-Content -LiteralPath $hostsPath -Value "# ESPN OUTAGE TEST END" -ErrorAction Stop
    & ipconfig.exe /flushdns

    # STEP 4: Verify domains are blocked.
    Test-EspnDomains "AFTER BLOCKING"

    Write-Host "`n====================================="
    Write-Host "ESPN API OUTAGE SIMULATION ACTIVE" -ForegroundColor Green
    Write-Host "====================================="
    Write-Host "`nYou can now test your NBA website."
    Write-Host "Restart the backend if it was already running."
    Write-Host "`nPress ANY KEY to restore ESPN access..." -ForegroundColor Yellow
    [void][Console]::ReadKey($true)
}
finally {
    # STEP 5: Restore original hosts file even if an error occurs.
    if ($backupCreated) {
        Write-Host "`nRestoring original hosts file..." -ForegroundColor Cyan
        try {
            Copy-Item -LiteralPath $backupPath -Destination $hostsPath -Force -ErrorAction Stop
            Write-Host "Original hosts file restored." -ForegroundColor Green
            Write-Host "ESPN API access should now be available." -ForegroundColor Green
            Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue
        }
        catch {
            Write-Host "RESTORE FAILED: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "Backup is located at: $backupPath"
        }
    }
}
