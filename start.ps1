Set-Location $PSScriptRoot

$provider = "gigachat"
$envPath = Join-Path $PSScriptRoot ".env"
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^\s*LLM_PROVIDER\s*=\s*(.+)\s*$') {
            $provider = $Matches[1].Trim().Trim('"').ToLower()
        }
    }
}

Write-Host "Поднимаю локальный сервис ГУ-23 (провайдер: $provider)..."
if ($provider -eq "gigachat") {
    Write-Host "Нужен GIGACHAT_AUTH_KEY в файле .env (скопируйте .env.example)."
} else {
    Write-Host "Ollama скачает модель (~4.7 ГБ). В Docker Desktop лучше дать от 8 ГБ RAM."
}
Write-Host ""

$composeArgs = @("up", "-d", "--build")
if ($provider -eq "ollama") {
    $composeArgs = @("--profile", "ollama") + $composeArgs
}

docker compose @composeArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker не смог стартовать. Проверьте, что Docker Desktop запущен."
    exit 1
}

Write-Host ""
Write-Host "Откройте http://localhost:8000"
Write-Host "Остановить: docker compose down"
