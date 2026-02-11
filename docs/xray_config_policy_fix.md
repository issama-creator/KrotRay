# Исправление конфигурации Policy для Stats API

## Если видишь ошибку «connections not found»

Если при проверке `get_connections()` в логах или при тесте видишь:
```text
StatusCode.NOT_FOUND
details = "user>>>UUID>>>connections not found."
```
это значит, что **Xray не собирает статистику соединений**. Нужно добавить в конфиг Xray секцию `policy.system` (см. ниже) и перезапустить Xray. После этого статистика начнёт собираться и ограничение устройств заработает.

---

## Проблема

Текущая конфигурация:
```json
"policy": {
  "levels": {
    "0": {
      "statsUserUplink": true,
      "statsUserDownlink": true
    }
  }
}
```

**Этого недостаточно** для работы Stats API для получения количества соединений (`connections`).

## Решение

Нужно **добавить** секцию `system` в `policy`. Можно оставить и `levels`, если нужна статистика трафика по пользователям.

### Правильная конфигурация:

```json
{
  "log": {
    "loglevel": "warning"
  },
  "api": {
    "tag": "api",
    "services": ["HandlerService", "StatsService"]
  },
  "stats": {},
  "policy": {
    "system": {
      "statsInboundUplink": true,
      "statsInboundDownlink": true,
      "statsOutboundUplink": true,
      "statsOutboundDownlink": true
    },
    "levels": {
      "0": {
        "statsUserUplink": true,
        "statsUserDownlink": true
      }
    }
  }
}
```

## Что изменилось

**Добавлено:**
```json
"system": {
  "statsInboundUplink": true,
  "statsInboundDownlink": true,
  "statsOutboundUplink": true,
  "statsOutboundDownlink": true
}
```

**Это необходимо** для того, чтобы Xray отслеживал соединения на уровне inbound/outbound и создавал статистику вида `"user>>>UUID>>>connections"`.

## Как применить

1. Отредактируйте `/usr/local/etc/xray/config.json` на сервере Xray
2. Добавьте секцию `"system"` в `"policy"` (как показано выше)
3. Проверьте конфиг:
   ```bash
   /usr/local/bin/xray -test -config /usr/local/etc/xray/config.json
   ```
4. Перезапустите Xray:
   ```bash
   systemctl restart xray
   ```

## Проверка работы

После перезапуска Xray должен начать собирать статистику соединений. Worker сможет получать количество активных соединений через `get_connections(uuid)`.

## Важно

- `levels` можно оставить — это для статистики трафика по пользователям
- `system` **обязательно** — это для статистики соединений (connections)
- Оба могут работать одновременно


