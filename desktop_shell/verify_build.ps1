# ---------------------------------------------------------------------------
# verify_build.ps1 -- post-build smoke gate for the frozen desktop shell.
#
# Launches a built ldcc artifact, waits for its real "L&D Command Center"
# window, and fails the gate if (a) no window appears before the timeout, or
# (b) an error / "Unhandled exception in script" dialog is visible instead.
#
# WHY THIS EXISTS (2026-09-13): the previous release shipped dist\ldcc.exe
# that died at startup with a silent PyInstaller dialog and no window - the
# console build showed the real traceback, but nothing automated caught it.
# This script makes the windowed launch a *verified pipeline stage*:
# build_release.bat and CI both run it after every build.
#
# Exit codes:
#   0  PASS - main window rendered, no error dialog
#   1  FAIL - window missing, early exit, or error dialog found
#   2  INVALID - usage / exe missing
#
# Escape hatches (documented in docs/DEPLOYMENT_PIPELINE.md):
#   LDCC_SKIP_SMOKE=1  -> PASS without launching (headless / bastion hosts)
# ---------------------------------------------------------------------------

param(
    [string]$ExePath,
    [int]$TimeoutSec = 120,
    [string]$WindowTitle = "L&D Command Center"
)

$ErrorActionPreference = "Stop"

if ($null -ne $env:LDCC_SKIP_SMOKE) {
    Write-Host "VERIFY SKIPPED (LDCC_SKIP_SMOKE set by caller)"
    exit 0
}

if (-not $ExePath) {
    $candidate = Join-Path (Split-Path $PSScriptRoot -Parent) "dist\ldcc.exe"
    if (Test-Path -LiteralPath $candidate) {
        $ExePath = $candidate
    }
}

if (-not $ExePath -or -not (Test-Path -LiteralPath $ExePath)) {
    Write-Host "VERIFY INVALID: exe not found: '$ExePath'"
    exit 2
}

$ExePath = (Resolve-Path -LiteralPath $ExePath).Path
$ExeName = [System.IO.Path]::GetFileNameWithoutExtension($ExePath)
$WorkDir = Split-Path -Parent $ExePath

# Window enumerator (add once per session; harmless on repeat).
if (-not ("LdccWinEnum" -as [type])) {
    Add-Type @"
    using System;
    using System.Collections.Generic;
    using System.Text;
    using System.Runtime.InteropServices;
    public class LdccWinEnum {
        public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
        [DllImport("user32.dll")]
        public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        public static extern int GetWindowText(IntPtr hWnd, StringBuilder sb, int max);
        [DllImport("user32.dll")]
        public static extern bool IsWindowVisible(IntPtr hWnd);
        [DllImport("user32.dll")]
        public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
        public static List<string> VisibleTitlesOf(uint pid) {
            var out_ = new List<string>();
            EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
                uint p;
                GetWindowThreadProcessId(hWnd, out p);
                if (p == pid && IsWindowVisible(hWnd)) {
                    var sb = new StringBuilder(512);
                    GetWindowText(hWnd, sb, 512);
                    string t = sb.ToString();
                    if (t.Length > 0) out_.Add(t);
                }
                return true;
            }, IntPtr.Zero);
            return out_;
        }
    }
"@
}

Write-Host "VERIFY launching: $ExePath (timeout ${TimeoutSec}s, watch: '$WindowTitle')"
$proc = Start-Process -FilePath $ExePath -WorkingDirectory $WorkDir -PassThru

$mainFound = $false
$badDialog = $null
$livePids = @()

for ($i = 0; $i -lt $TimeoutSec; $i += 3) {
    # Collect every process with the artifact's name (onefile parent + child).
    foreach ($p in Get-Process -Name $ExeName -ErrorAction SilentlyContinue) {
        $livePids += $p.Id
        $titles = [LdccWinEnum]::VisibleTitlesOf([uint32]$p.Id)
        foreach ($t in $titles) {
            if ($t -like "*$WindowTitle*") { $mainFound = $true }
            if ($t -like "*Unhandled exception*" -or $t -match "Error") {
                $badDialog = $t
            }
        }
        if ($mainFound -and -not $badDialog) {
            Write-Host "VERIFY PASS: window '$WindowTitle' rendered in ~$($i)s (pid $($p.Id))"
            break
        }
    }
    if ($mainFound -and -not $badDialog) { break }
    if ($proc.HasExited) {
        Write-Host "VERIFY FAIL: process exited early with code $($proc.ExitCode) at t=${i}s"
        exit 1
    }
    Start-Sleep -Seconds 3
}

if ($badDialog) {
    Write-Host "VERIFY FAIL: error dialog visible: '$badDialog'"
    foreach ($p in Get-Process -Name $ExeName -ErrorAction SilentlyContinue) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
    exit 1
}

if (-not $mainFound) {
    Write-Host "VERIFY FAIL: no window '$WindowTitle' within ${TimeoutSec}s"
    foreach ($p in Get-Process -Name $ExeName -ErrorAction SilentlyContinue) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
    exit 1
}

# PASS: leave the app running so a human can inspect, unless killed explicitly.
Write-Host "VERIFY PASS: artifact windowed-launch verified clean"