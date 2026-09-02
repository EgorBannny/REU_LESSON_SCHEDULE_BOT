#!/bin/bash
set -e

cd ~/REU_LESSON_SCHEDULE_BOT/

echo "=== Обновление кода ==="
cp .env /tmp/.env.backup 2>/dev/null || true

git fetch origin main
git reset --hard origin/main

cp /tmp/.env.backup .env 2>/dev/null || echo "WARN: .env не найден в бэкапе!"

echo "=== Перезапуск Бот-сервиса ==="
curl -X POST --basic --user "${ALWAYSDATA_TOKEN} account=${ACCOUNT_NAME}:" https://api.alwaysdata.com/v1/service/${SERVICE_ID}/restart/
echo "Запрос на перезапуск сервиса ${SERVICE_ID} отправлен."
