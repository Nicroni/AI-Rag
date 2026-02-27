# PowerShell Queries For Windows Logs

Use these snippets for fast evidence extraction.

## Last N critical/error in System

```powershell
Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2} -MaxEvents 100 |
  Select-Object TimeCreated, Id, ProviderName, LevelDisplayName, Message
```

## Event IDs in time window

```powershell
$start = (Get-Date).AddHours(-2)
$end = Get-Date
Get-WinEvent -FilterHashtable @{
  LogName='System'
  Id=41,6008,7031,7034
  StartTime=$start
  EndTime=$end
} | Select-Object TimeCreated, Id, ProviderName, Message
```

## Security failed logons (4625)

```powershell
Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4625; StartTime=(Get-Date).AddHours(-6)} |
  Select-Object TimeCreated, Id, Message
```

## App crashes (1000/1002/1026)

```powershell
Get-WinEvent -FilterHashtable @{
  LogName='Application'
  Id=1000,1002,1026
  StartTime=(Get-Date).AddHours(-6)
} | Select-Object TimeCreated, Id, ProviderName, Message
```

## Service install/change indicators

```powershell
Get-WinEvent -FilterHashtable @{LogName='System'; Id=7040,7045; StartTime=(Get-Date).AddDays(-1)} |
  Select-Object TimeCreated, Id, Message
```

## Export timeline to CSV

```powershell
$events = Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).AddHours(-4)}
$events | Select-Object TimeCreated, Id, ProviderName, LevelDisplayName, Message |
  Export-Csv .\timeline_system.csv -NoTypeInformation -Encoding UTF8
```

