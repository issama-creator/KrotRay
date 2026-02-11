# Правка: NOT_FOUND при get_connections не должен выводить traceback

## Проблема

При вызове `get_connections()` Xray возвращает `StatusCode.NOT_FOUND` для статистики `user>>>UUID>>>connections`, если:
- статистика ещё не создана (пользователь не подключен), или
- в конфиге Xray нет `policy.system` (тогда статистика вообще не собирается).

Сейчас код логирует полный traceback. Нужно обрабатывать NOT_FOUND как «0 соединений» и не выводить traceback.

## Что сделать на сервере

Отредактировать файл `/opt/krotray/services/xray_client.py`.

### 1. Добавить импорт grpc в начале блока try в get_connections

В функции `get_connections` в блоке `try:` после строки:
```python
        import grpc
        from app.stats.command import command_pb2, command_pb2_grpc
```

убедись, что используется `grpc`. Далее — ловить ошибку.

### 2. Обернуть вызов GetStats в try/except

Найди блок (примерно так):

```python
        channel = grpc.insecure_channel(f"{host}:{grpc_port}")
        try:
            stub = command_pb2_grpc.StatsServiceStub(channel)
            request = command_pb2.GetStatsRequest(name=stats_name, reset=False)
            response = stub.GetStats(request)
            
            if response.stat and response.stat.name == stats_name:
                connections = response.stat.value
                logger.debug("Stats API: uuid=%s connections=%d", user_uuid, connections)
                return int(connections)
            else:
                logger.warning("Stats API: uuid=%s no stats found (name=%s)", user_uuid, stats_name)
                return 0
        finally:
            channel.close()
```

**Замени его на:**

```python
        channel = grpc.insecure_channel(f"{host}:{grpc_port}")
        try:
            stub = command_pb2_grpc.StatsServiceStub(channel)
            request = command_pb2.GetStatsRequest(name=stats_name, reset=False)
            try:
                response = stub.GetStats(request)
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.NOT_FOUND:
                    logger.debug(
                        "Stats API: uuid=%s connections not found (0), ok",
                        user_uuid,
                    )
                    return 0
                raise
            
            if response.stat and response.stat.name == stats_name:
                connections = response.stat.value
                logger.debug("Stats API: uuid=%s connections=%d", user_uuid, connections)
                return int(connections)
            else:
                return 0
        finally:
            channel.close()
```

Сохрани файл и перезапусти воркер (по желанию):
```bash
sudo systemctl restart krotray-device-limiter
```

После правки тест `get_connections` не будет выводить traceback при NOT_FOUND, а будет возвращать 0.

## Главное: включить сбор статистики в Xray

NOT_FOUND при **включённом** VPN с двух устройств значит, что Xray не создаёт статистику `user>>>UUID>>>connections`. Нужно на **сервере Xray** (103.137.251.165) в `/usr/local/etc/xray/config.json`:

1. Добавить в `api.services`: `"StatsService"`.
2. Добавить в `policy` секцию `system` с `statsInboundUplink`, `statsInboundDownlink`, `statsOutboundUplink`, `statsOutboundDownlink: true`.
3. Перезапустить Xray: `systemctl restart xray`.

Подробно — в `docs/xray_config_policy_fix.md`.
