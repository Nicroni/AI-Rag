# Authentication Incident Playbook (Windows)

Goal: determine why login/auth failed and whether it is benign, misconfig, or attack.

## Inputs Required

- Incident time window
- Affected account(s)
- Source host/IP if known
- Target host/service

## Primary Events

- `4625`: failed logon
- `4624`: successful logon
- `4648`: explicit credentials
- `4672`: elevated privileges
- `4768/4769/4771`: Kerberos flow (domain contexts)

## Decision Flow

1. Count failed logons per minute for target account
2. Check `Logon Type` patterns:
   - Type 2: interactive
   - Type 3: network
   - Type 10: remote interactive (RDP)
3. Parse `Status` + `SubStatus`:
   - wrong password
   - account locked/disabled
   - expired credentials
4. Look for nearby success (`4624`) from same source
5. If high-volume failures from many sources, treat as brute-force candidate

## Immediate Actions

- Lock or reset high-risk account
- Block source IP/range if attack-like
- Verify time sync and DC reachability for Kerberos anomalies
- Capture exact events for RCA report

## Output For RCA

- Root cause hypothesis
- Evidence list (event ID + timestamp + host)
- Mitigation applied
- Follow-up hardening actions

