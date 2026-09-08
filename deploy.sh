#!/bin/bash
set -e

cd ~/

echo "=== Обновление кода ==="
cp .env /tmp/.env.backup 2>/dev/null || true

git fetch origin main
git reset --hard origin/main

cp /tmp/.env.backup .env 2>/dev/null || echo "WARN: .env не найден в бэкапе!"

echo "=== Перезапуск Бот-сервиса ==="
echo "=== Перезапуск Docker-сервисов ==="
dokcer compose up -d --build

echo "=== Очистка старых образов ==="
docker image prune -f