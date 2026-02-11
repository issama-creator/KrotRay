# Инструкция по проверке системы ограничения устройств

## 1. Проверка статуса Worker

### Проверить, что worker запущен и работает:

```bash
sudo systemctl status krotray-device-limiter
```

**Ожидаемый результат:**
```
Active: active (running)
```

### Просмотр логов worker'а:

```bash
sudo journalctl -u krotray-device-limiter -n 50 --no-pager
```

**Ожидаемые логи:**
```
[INFO] Device limiter worker запущен (интервал проверки: 60 сек)
[INFO] Проверка X активных подписок
```

Если видите ошибки — проверьте конфигурацию и подключение к БД/Xray.

---

## 2. Проверка подключения к Xray Stats API

### Тест получения статистики соединений (на сервере с ботом):

```bash
cd /opt/krotray
source venv/bin/activate
python3 -c "
from services.xray_client import get_connections
from db.session import SessionLocal
from db.models import Subscription, Server

db = SessionLocal()
# Найти активную подписку с UUID
sub = db.execute('SELECT * FROM subscriptions WHERE uuid IS NOT NULL AND status = \\'active\\' LIMIT 1').first()
if sub:
    server = db.execute('SELECT * FROM servers WHERE id = {}'.format(sub.server_id)).first()
    if server:
        conns = get_connections(server.host, server.grpc_port, sub.uuid)
        print(f'UUID: {sub.uuid}')
        print(f'Server: {server.host}:{server.grpc_port}')
        print(f'Active connections: {conns}')
        print(f'Allowed devices: {sub.allowed_devices}')
    else:
        print('Server not found')
else:
    print('No active subscription found')
db.close()
"
```

**Ожидаемый результат:**
- Если пользователь подключен: `Active connections: 1` (или больше)
- Если не подключен: `Active connections: 0` (или ошибка NOT_FOUND, которая обрабатывается как 0)

---

## 3. Проверка данных в базе данных

### Проверить подписки с лимитами устройств:

```bash
cd /opt/krotray
source venv/bin/activate
python3 -c "
from db.session import SessionLocal
from sqlalchemy import text

db = SessionLocal()
result = db.execute(text('''
    SELECT 
        id, user_id, uuid, status, 
        allowed_devices, disabled_by_limit, violation_count,
        expires_at
    FROM subscriptions 
    WHERE uuid IS NOT NULL 
    ORDER BY created_at DESC 
    LIMIT 5
'''))
for row in result:
    print(f'ID: {row[0]}, User: {row[1]}, UUID: {row[2][:8]}...')
    print(f'  Status: {row[3]}, Allowed: {row[4]}, Disabled: {row[5]}, Violations: {row[6]}')
    print(f'  Expires: {row[7]}')
    print()
db.close()
"
```

**Ожидаемый результат:**
- `allowed_devices` должен быть 1, 2, 3, 4 или 5 (в зависимости от платежа)
- `disabled_by_limit` должен быть `False` для нормальных подписок
- `violation_count` должен быть 0 для нормальных подписок

---

## 4. Тестирование превышения лимита (практический тест)

### Шаг 1: Создать тестовую подписку с лимитом 1 устройство

1. Через мини-приложение оплатите тариф на **1 устройство**
2. Подключите VPN на одном устройстве (например, телефон)
3. Проверьте, что подключение работает

### Шаг 2: Подключить второе устройство

1. Используйте тот же UUID на втором устройстве (например, компьютер)
2. Подождите **2-3 минуты** (worker проверяет каждые 60 секунд, нужно 2 проверки для `violation_count >= 2`)

### Шаг 3: Проверить отключение

```bash
sudo journalctl -u krotray-device-limiter -n 20 --no-pager | grep -E "превышение|отключен|violation"
```

**Ожидаемые логи:**
```
[WARNING] Subscription X: превышение лимита! connections=2 > allowed=1 violation_count=1
[WARNING] Subscription X: превышение лимита! connections=2 > allowed=1 violation_count=2
[INFO] Subscription X: пользователь отключен из-за превышения лимита устройств
```

### Шаг 4: Проверить статус в БД

```bash
cd /opt/krotray
source venv/bin/activate
python3 -c "
from db.session import SessionLocal
from sqlalchemy import text

db = SessionLocal()
result = db.execute(text('''
    SELECT id, uuid, allowed_devices, disabled_by_limit, violation_count
    FROM subscriptions 
    WHERE uuid IS NOT NULL 
    ORDER BY created_at DESC 
    LIMIT 1
'''))
row = result.first()
if row:
    print(f'Subscription ID: {row[0]}')
    print(f'UUID: {row[1][:8]}...')
    print(f'Allowed devices: {row[2]}')
    print(f'Disabled by limit: {row[3]}')
    print(f'Violation count: {row[4]}')
    if row[3]:
        print('✅ Пользователь отключен (как и ожидалось)')
    else:
        print('⚠️ Пользователь не отключен (возможно, еще не прошло 2 проверки)')
db.close()
"
```

**Ожидаемый результат:**
- `disabled_by_limit: True`
- `violation_count: 2` (или больше)
- VPN должен перестать работать на обоих устройствах

### Шаг 5: Отключить второе устройство и проверить восстановление

1. Отключите VPN на втором устройстве
2. Подождите **1-2 минуты**

**Проверить логи:**
```bash
sudo journalctl -u krotray-device-limiter -n 20 --no-pager | grep -E "включен|соединения в норме"
```

**Ожидаемые логи:**
```
[INFO] Subscription X: соединения в норме, violation_count сброшен
[INFO] Subscription X: пользователь автоматически включен (соединения в норме)
```

**Проверить БД:**
```bash
cd /opt/krotray
source venv/bin/activate
python3 -c "
from db.session import SessionLocal
from sqlalchemy import text

db = SessionLocal()
result = db.execute(text('''
    SELECT disabled_by_limit, violation_count
    FROM subscriptions 
    WHERE uuid IS NOT NULL 
    ORDER BY created_at DESC 
    LIMIT 1
'''))
row = result.first()
if row:
    print(f'Disabled by limit: {row[0]}')
    print(f'Violation count: {row[1]}')
    if not row[0] and row[1] == 0:
        print('✅ Пользователь автоматически включен (как и ожидалось)')
    else:
        print('⚠️ Статус еще не обновился')
db.close()
"
```

**Ожидаемый результат:**
- `disabled_by_limit: False`
- `violation_count: 0`
- VPN должен снова работать на первом устройстве

---

## 5. Проверка через gRPC напрямую (продвинутый тест)

### На сервере с Xray, проверить Stats API:

```bash
# Установить grpcurl (если нет)
# Ubuntu/Debian:
apt install grpcurl

# Или скачать бинарник:
# wget https://github.com/fullstorydev/grpcurl/releases/download/v1.8.9/grpcurl_1.8.9_linux_x86_64.tar.gz

# Получить статистику соединений для UUID (замените UUID на реальный)
grpcurl -plaintext -d '{"name": "user>>>ВАШ_UUID>>>connections", "reset": false}' \
  localhost:8081 app.stats.command.StatsService/GetStats
```

**Ожидаемый результат:**
```json
{
  "stat": {
    "name": "user>>>UUID>>>connections",
    "value": 1
  }
}
```

Если `value: 0` или ошибка `NOT_FOUND` — пользователь не подключен или статистика не собирается.

---

## 6. Проверка Handler API (enable/disable)

### Тест отключения пользователя:

```bash
cd /opt/krotray
source venv/bin/activate
python3 -c "
from services.xray_client import disable_user, enable_user
from db.session import SessionLocal
from db.models import Subscription, Server

db = SessionLocal()
sub = db.execute('SELECT * FROM subscriptions WHERE uuid IS NOT NULL AND status = \\'active\\' LIMIT 1').first()
if sub:
    server = db.execute('SELECT * FROM servers WHERE id = {}'.format(sub.server_id)).first()
    if server:
        email = f'user_{sub.user_id}'
        print(f'Testing disable/enable for UUID: {sub.uuid[:8]}...')
        print(f'Server: {server.host}:{server.grpc_port}')
        
        # Отключить
        print('\\n1. Disabling user...')
        try:
            disable_user(server.host, server.grpc_port, sub.uuid, email)
            print('✅ User disabled successfully')
        except Exception as e:
            print(f'❌ Error disabling: {e}')
        
        # Включить обратно
        print('\\n2. Enabling user...')
        try:
            enable_user(server.host, server.grpc_port, sub.uuid, email)
            print('✅ User enabled successfully')
        except Exception as e:
            print(f'❌ Error enabling: {e}')
    else:
        print('Server not found')
else:
    print('No active subscription found')
db.close()
"
```

**Ожидаемый результат:**
- Оба вызова должны завершиться без ошибок
- В логах Xray должны появиться записи о добавлении/удалении пользователя

---

## 7. Мониторинг в реальном времени

### Следить за логами worker'а в реальном времени:

```bash
sudo journalctl -u krotray-device-limiter -f
```

**Что смотреть:**
- Каждые 60 секунд должны появляться логи `[INFO] Проверка X активных подписок`
- При превышении лимита: `[WARNING] превышение лимита!`
- При отключении: `[INFO] пользователь отключен`
- При восстановлении: `[INFO] пользователь автоматически включен`

---

## 8. Проверка конфигурации Xray

### Убедиться, что StatsService включен:

```bash
# На сервере Xray
cat /usr/local/etc/xray/config.json | grep -A 5 '"api"'
```

**Ожидаемый результат:**
```json
"api": {
  "tag": "api",
  "services": ["HandlerService", "StatsService"]
}
```

### Проверить policy.system:

```bash
cat /usr/local/etc/xray/config.json | grep -A 10 '"policy"'
```

**Ожидаемый результат:**
```json
"policy": {
  "system": {
    "statsInboundUplink": true,
    "statsInboundDownlink": true,
    "statsOutboundUplink": true,
    "statsOutboundDownlink": true
  },
  ...
}
```

---

## Чек-лист быстрой проверки

- [ ] Worker запущен и работает (`systemctl status`)
- [ ] Логи worker'а показывают периодические проверки
- [ ] В БД есть подписки с `allowed_devices > 0`
- [ ] `get_connections()` возвращает корректные значения (0 или больше)
- [ ] При превышении лимита пользователь отключается через 2 проверки
- [ ] При восстановлении пользователь автоматически включается
- [ ] Xray config.json содержит `StatsService` и `policy.system`

---

## Возможные проблемы

### Worker не запускается:
- Проверьте `PYTHONPATH` в systemd сервисе
- Проверьте права доступа к файлам
- Проверьте логи: `journalctl -u krotray-device-limiter -n 50`

### `get_connections()` всегда возвращает 0:
- Проверьте, что `StatsService` включен в Xray config
- Проверьте, что `policy.system` настроен правильно
- Убедитесь, что пользователь действительно подключен к VPN

### Пользователь не отключается:
- Проверьте, что `violation_count >= 2` (нужно 2 проверки подряд)
- Проверьте логи worker'а на ошибки gRPC
- Проверьте подключение к Xray gRPC API

### Пользователь не включается обратно:
- Проверьте, что `connections <= allowed_devices`
- Проверьте логи на ошибки `enable_user()`
- Убедитесь, что worker работает и проверяет подписки
