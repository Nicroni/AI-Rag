# High-Value Windows Event IDs

Use this as a quick lookup during outage and security triage.

## System / Stability

- `41` (Kernel-Power): unexpected reboot/power loss
- `6008`: previous shutdown was unexpected
- `1001` (BugCheck): BSOD details/minidump reference
- `1074`: planned restart/shutdown (process/user reason)
- `6005`: Event Log service started (boot marker)
- `6006`: Event Log service stopped (shutdown marker)

## Service Control Manager

- `7031`: service terminated unexpectedly (with restart actions)
- `7034`: service terminated unexpectedly (no recovery details)
- `7040`: service start type changed
- `7045`: new service installed (important for persistence checks)

## Application Crashes

- `1000` (Application Error): app crash faulting module/exception code
- `1002` (Application Hang): app unresponsive
- `1026` (.NET Runtime): managed exception context

## Security (Auth + Privilege)

- `4624`: successful logon
- `4625`: failed logon (reason/status/substatus)
- `4634`: logoff
- `4648`: explicit credentials used
- `4672`: special privileges assigned
- `4688`: process created (if auditing enabled)
- `4720`: user account created
- `4726`: user account deleted
- `4719`: audit policy changed

## Domain/Auth (If server is AD/DC relevant)

- `4768`: Kerberos TGT requested
- `4769`: Kerberos service ticket requested
- `4771`: Kerberos pre-auth failed

## Interpretation Notes

- Treat one event ID in isolation as weak evidence.
- Prioritize correlations: same host + same time + related channels.
- Always pair event evidence with service/app health metrics.

