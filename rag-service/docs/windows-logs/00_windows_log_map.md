# Windows Log Map For RAG

This document defines where to look first during Windows production incidents.

## Core Log Channels

- `System`: OS, driver, service, kernel, boot, hardware errors
- `Application`: app crashes, .NET/runtime issues, app-specific errors
- `Security`: authentication, authorization, account changes, process creation (if auditing enabled)
- `Setup`: installation/update events
- `Microsoft-Windows-TaskScheduler/Operational`: task runs/failures
- `Microsoft-Windows-WindowsUpdateClient/Operational`: update lifecycle
- `Microsoft-Windows-DNS-Client/Operational`: client DNS issues
- `Microsoft-Windows-GroupPolicy/Operational`: GPO application failures
- `Microsoft-Windows-TerminalServices-*`: RDP login/session issues

## First 5-Minute Triage Path

1. Confirm incident time window (start/end UTC/local)
2. Query `System` around the window for critical/error
3. Query `Application` for app crash markers
4. Query `Security` for suspicious login/process events
5. Build timeline: trigger -> impact -> recovery action

## Severity Hints

- `Critical` in `System` near outage window is high signal
- Repeating same Event ID with short interval often indicates root cause loop
- Single warning without impact metrics is usually secondary signal

