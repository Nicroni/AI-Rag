# Windows Logs Knowledge Pack

This folder is prepared for RAG indexing focused on Windows production troubleshooting.

Files:

- `00_windows_log_map.md` - channel map and first 5-minute triage
- `01_high_value_event_ids.md` - event ID cheat sheet
- `02_auth_incident_playbook.md` - authentication incident flow
- `03_service_crash_playbook.md` - service failure root cause guide
- `04_powershell_queries.md` - practical log query snippets
- `05_rca_response_template.md` - production RCA answer format

## Re-index Command

```powershell
$body = @{
  path = "D:\LLM\llama.cpp\rag-service\docs"
  collection = "kb_docs"
  recursive = $true
  rebuild = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8090/index" -ContentType "application/json; charset=utf-8" -Body $body
```

