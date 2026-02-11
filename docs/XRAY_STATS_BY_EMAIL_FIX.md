# Правка: статистика connections по email, а не по UUID

В Xray пользовательская статистика привязана к **email** (идентификатору пользователя при AddUser), а не к UUID. Нужно запрашивать `user>>>user_1>>>connections`, а не `user>>>uuid>>>connections`.

## 1. Правка `services/xray_client.py` на сервере

Открой файл:
```bash
nano /opt/krotray/services/xray_client.py
```

### 1.1 Сигнатура и имя статистики

Найди функцию `get_connections` (примерно строка 19):

```python
def get_connections(host: str, grpc_port: int, user_uuid: str) -> int:
```

**Замени на** (добавлен параметр `email`):

```python
def get_connections(host: str, grpc_port: int, user_uuid: str, email: str | None = None) -> int:
```

Найди строку с именем статистики (примерно 33–34):

```python
        stats_name = f"user>>>{user_uuid}>>>connections"
```

**Замени на** (если передан email — используем его):

```python
        # Xray считает статистику по email пользователя, не по UUID
        if email:
            stats_name = f"user>>>{email}>>>connections"
        else:
            stats_name = f"user>>>{user_uuid}>>>connections"
```

### 1.2 Обработка NOT_FOUND (без traceback)

В том же блоке найди:
```python
            request = command_pb2.GetStatsRequest(name=stats_name, reset=False)
            response = stub.GetStats(request)
```

**Замени на**:
```python
            request = command_pb2.GetStatsRequest(name=stats_name, reset=False)
            try:
                response = stub.GetStats(request)
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.NOT_FOUND:
                    logger.debug("Stats API: name=%s not found (0)", stats_name)
                    return 0
                raise
```

Сохрани файл (Ctrl+O, Enter, Ctrl+X).

---

## 2. Правка `workers/device_limiter.py` на сервере

Открой файл:
```bash
nano /opt/krotray/workers/device_limiter.py
```

Найди вызов `get_connections` (примерно строка 47):

```python
        connections = get_connections(server.host, server.grpc_port, subscription.uuid)
```

**Замени на** (передаём email):

```python
        connections = get_connections(
            server.host,
            server.grpc_port,
            subscription.uuid,
            email=email,
        )
```

(Переменная `email = f"user_{subscription.user_id}"` уже есть выше в этой функции.)

Сохрани файл.

---

## 3. Перезапуск воркера

```bash
sudo systemctl restart krotray-device-limiter
```

---

## 4. Проверка

Подключись к VPN с одного устройства, затем на сервере бота выполни (подставь свой user_id, например 1):

```bash
cd /opt/krotray && source venv/bin/activate
python3 -c "
from services.xray_client import get_connections
# Хост и порт Xray из таблицы servers (103.137.251.165, 8081)
# Подставь user_id своей подписки
email = 'user_1'
c = get_connections('103.137.251.165', 8081, 'any-uuid', email=email)
print(f'connections (email={email}): {c}')
"
```

Если Xray отдаёт статистику по email, увидишь `connections: 1`. Если снова 0 — пришли вывод этой команды и версию Xray (`xray version`).
