# Настройка ограничения устройств (Device Limit)

## Что было реализовано

1. ✅ Добавлены поля в БД:
   - `subscriptions.allowed_devices` (INTEGER, default=1)
   - `subscriptions.disabled_by_limit` (BOOLEAN, default=false)
   - `subscriptions.violation_count` (INTEGER, default=0)
   - `payments.devices` (INTEGER, default=1)

2. ✅ Создан gRPC клиент для Xray Stats API (`services/xray_client.py`):
   - `get_connections()` - получение количества активных соединений
   - `disable_user()` - отключение пользователя
   - `enable_user()` - включение пользователя

3. ✅ Создан worker (`workers/device_limiter.py`):
   - Проверяет активные подписки каждые 60 секунд
   - Отключает пользователей при превышении лимита (violation_count >= 2)
   - Автоматически включает пользователей при восстановлении нормы

4. ✅ Обновлена логика создания подписки:
   - `allowed_devices` сохраняется из платежа при создании/продлении подписки

## Шаги для развертывания

### 1. Включить Stats API в конфиге Xray

**ВАЖНО:** Это нужно сделать вручную на каждом сервере Xray!

Отредактируйте `/usr/local/etc/xray/config.json` и убедитесь, что есть:

```json
{
  "api": {
    "tag": "api",
    "services": ["HandlerService", "StatsService"]
  },
  "policy": {
    "system": {
      "statsInboundUplink": true,
      "statsInboundDownlink": true,
      "statsOutboundUplink": true,
      "statsOutboundDownlink": true
    }
  },
  "stats": {}
}
```

После изменения:
```bash
systemctl restart xray
```

### 2. Применить миграции БД

```bash
cd /opt/krotray
source venv/bin/activate
alembic upgrade head
```

Это создаст поля:
- `subscriptions.allowed_devices`
- `subscriptions.disabled_by_limit`
- `subscriptions.violation_count`
- `payments.devices`

### 3. Сгенерировать proto для Stats API

```bash
cd /opt/krotray
source venv/bin/activate
bash scripts/generate_xray_proto.sh
```

Это создаст Python модули из `proto_xray/app/stats/command/command.proto`.

### 4. Установить systemd service

```bash
sudo cp workers/krotray-device-limiter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable krotray-device-limiter
sudo systemctl start krotray-device-limiter
```

Проверить статус:
```bash
sudo systemctl status krotray-device-limiter
```

Просмотр логов:
```bash
sudo journalctl -u krotray-device-limiter -f
```

## Как это работает

1. **При оплате:** Пользователь выбирает количество устройств (1-5), это сохраняется в `payments.devices` и затем в `subscriptions.allowed_devices`.

2. **Worker каждые 60 секунд:**
   - Берет все активные подписки с UUID и server_id
   - Для каждой подписки вызывает `get_connections(uuid)` через Stats API
   - Если `connections > allowed_devices`:
     - Увеличивает `violation_count`
     - Если `violation_count >= 2`: отключает пользователя через `disable_user()`
   - Если `connections <= allowed_devices`:
     - Сбрасывает `violation_count = 0`
     - Если пользователь был отключен (`disabled_by_limit = true`): включает обратно через `enable_user()`

3. **Без перезапуска Xray:** Используется только gRPC API, Xray не перезапускается, UUID не меняется.

## Проверка работы

1. Создайте тестовую подписку с `allowed_devices = 1`
2. Подключитесь с двух устройств одновременно
3. Через ~2 минуты (2 проверки по 60 сек) пользователь должен быть отключен
4. Отключите одно устройство
5. Через ~1 минуту пользователь должен автоматически включиться

## Важные замечания

- **Stats API должен быть включен** в конфиге Xray на всех серверах
- Worker работает как отдельный процесс, не внутри FastAPI
- UUID пользователя **не меняется** при отключении/включении
- Xray **не перезапускается** - используется только gRPC API
- Лимит устройств берется из платежа и сохраняется в подписке
