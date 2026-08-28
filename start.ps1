Set-Location $PSScriptRoot

Write-Host "Поднимаю локальный сервис ГУ-23..."
Write-Host "Первый запуск скачает модель (~4.7 ГБ). В Docker Desktop лучше дать от 8 ГБ RAM."
Write-Host ""

docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker не смог стартовать. Проверьте, что Docker Desktop запущен."
    exit 1
}

Write-Host ""
Write-Host "Откройте http://localhost:8000"
Write-Host "Статус скачивания модели виден на странице."
Write-Host "Остановить: docker compose down"
