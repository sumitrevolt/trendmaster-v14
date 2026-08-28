try {
  $h = Invoke-WebRequest -Uri 'https://shadow-cosmos-unending.ngrok-free.dev/health' -TimeoutSec 8
  Write-Output ("HEALTH " + $h.StatusCode + " : " + $h.Content)
} catch {
  Write-Output ("HEALTH FAIL: " + $_.Exception.Message)
}
Write-Output "---"
try {
  $s = Invoke-WebRequest -Uri 'https://shadow-cosmos-unending.ngrok-free.dev/status' -TimeoutSec 8
  Write-Output ("STATUS " + $s.StatusCode + " : " + $s.Content)
} catch {
  Write-Output ("STATUS FAIL: " + $_.Exception.Message)
}
