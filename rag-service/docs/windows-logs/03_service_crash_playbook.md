# Service Crash Playbook (Windows)

Goal: identify root cause when a Windows service repeatedly fails or restarts.

## Key Events

- `7031`, `7034` (SCM): service unexpectedly terminated
- `7040`: start type changes
- `1000`, `1026`: app/runtime crash context

## Triage Steps

1. Identify failing service name
2. Build crash timeline from `System` + `Application`
3. Confirm restart policy and restart frequency
4. Check dependency services and startup order
5. Check recent config/update/deployment changes

## High-Confidence Root Cause Patterns

- Missing dependency after update -> service start failure chain
- Repeated `7031` + app crash `1000` with same module -> binary/runtime issue
- Start type changed (`7040`) before outage -> misconfiguration

## Fast Mitigation

- Roll back latest service/app config
- Restart dependency services in order
- Restore known-good binary/config
- Temporarily set delayed start if boot race condition suspected

## Evidence Template

- Host:
- Service:
- First failure time:
- Repeating Event IDs:
- Fault module/exception:
- Change before incident:
- Mitigation result:

