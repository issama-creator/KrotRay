# Чек-лист: проверка Xray + бот (запись юзера, ключ, отключение)

Проверь по шагам на **сервере с ботом (krotray.ru)** и на **сервере Xray (103.137.251.165)**.

---

## 1. Конфиг Xray на 103.137.251.165

### 1.1 Включён ли gRPC API

В конфиге Xray должен быть блок **API** и **inbound для API** (или настройка, которая поднимает gRPC-сервер).

Пример (фрагмент):

```json
{
  "api": {
    "tag": "api",
    "services": [
      "HandlerService"
    ]
  },
  "inbounds": [
    {
      "tag": "api",
      "port": 8080,
      "listen": "127.0.0.1",
      "protocol": "dokodemo-door",
      "settings": {
        "address": "127.0.0.1"
      },
      "sniffing": null,
      "streamSettings": null
    }
  ],
  "routing": {
    "rules": [
      {
        "type": "field",
        "inboundTag": ["api"],
        "outboundTag": "api"
      }
    ]
  },
  "outbounds": [
    { "tag": "api", "protocol": "blackhole" }
  ]
}
```

Важно:
- Порт API (в примере `8080`) — это и есть **XRAY_GRPC_PORT** в `.env` на боте.
- Если API слушает только `127.0.0.1`, с другого сервера (krotray.ru) до него не достучаться. Тогда нужно либо слушать `0.0.0.0:8080`, либо поднять отдельный inbound для API на внешнем интерфейсе (и открыть этот порт в файрволе).

**Проверка:** на 103.137.251.165 выполни:
```bash
ss -tlnp | grep 8080
# или
netstat -tlnp | grep 8080
```
Должен быть процесс Xray, слушающий порт API (8080 или тот, что у тебя).

---

### 1.2 Тег VLESS inbound

В конфиге Xray найди **inbound с протоколом VLESS** (Reality и т.п.). У него есть поле **`"tag"`**.

Пример:

```json
{
  "tag": "vless-in",
  "port": 443,
  "protocol": "vless",
  "settings": { ... },
  "sniffing": { ... },
  "streamSettings": { ... }
}
```

Значение **`tag`** (в примере `vless-in`) должно **совпадать** с **XRAY_INBOUND_TAG** в `.env` на боте. Если у тебя, например, `"tag": "vless-reality"`, то в `.env` должно быть:
```env
XRAY_INBOUND_TAG=vless-reality
```

**Проверка:** открой конфиг Xray и выпиши точное значение `tag` у VLESS inbound. Поставь такое же в `.env` на krotray.ru.

---

## 2. Доступность порта gRPC с krotray.ru

Бот работает на **krotray.ru**. Он должен достучаться до **103.137.251.165:XRAY_GRPC_PORT** по TCP.

**Проверка на сервере krotray.ru:**

```bash
# Подставь свой XRAY_GRPC_PORT (например 8080)
nc -zv 103.137.251.165 8080
```

- Если пишет `succeeded` или `Connected` — порт доступен.
- Если `Connection refused` — на 103.137.251.165 ничего не слушает этот порт или файрвол режет.
- Если таймаут — файрвол (на 103.137.251.165 или у хостера) блокирует входящие на этот порт.

**На сервере 103.137.251.165** открой порт API во входящем файрволе (ufw/iptables/панель хостера), чтобы с IP krotray.ru (или с любого IP, если так решил) был доступ на порт gRPC.

---

## 3. .env на VDS с ботом (krotray.ru)

В одной папке с ботом (например `/opt/krotray/.env`) проверь, что есть **все** нужные переменные и значения.

| Переменная | Что проверить |
|------------|----------------|
| `XRAY_INBOUND_TAG` | Точно как `tag` VLESS inbound в конфиге Xray (например `vless-in`). |
| `XRAY_SERVER_HOST` | `103.137.251.165` |
| `XRAY_GRPC_PORT` | Порт, на котором в Xray слушается gRPC API (например `8080`). |
| `VLESS_URL_TEMPLATE` | Одна строка, без переносов. Внутри обязательно `{uuid}`. Хост и порт в ссылке — те, куда подключается клиент (часто 103.137.251.165:443). |

Пример (подставь свои значения):

```env
XRAY_INBOUND_TAG=vless-in
XRAY_SERVER_NAME=Main
XRAY_SERVER_HOST=103.137.251.165
XRAY_GRPC_PORT=8080
XRAY_MAX_USERS=100

VLESS_URL_TEMPLATE=vless://{uuid}@103.137.251.165:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.apple.com&fp=chrome&pbk=OgH3-UkoJbWUhmz_bTPmUbRQbAOyRhIgQ841KI4C42w&sid=568d2499&type=tcp#KrotRay
```

**Проверка:**  
`grep -E "XRAY_|VLESS_" /opt/krotray/.env` — все переменные на месте, без лишних пробелов/кавычек.

---

## 4. Таблица `servers` в БД

Бот выбирает сервер из БД. Должна быть хотя бы одна запись с твоим Xray.

**Проверка на krotray.ru:**

```bash
cd /opt/krotray
source venv/bin/activate
sudo -u postgres psql -d krotray -c "SELECT id, name, host, grpc_port, active_users, max_users, enabled FROM servers;"
```

Ожидаемо: одна строка, `host=103.137.251.165`, `grpc_port` как в конфиге Xray, `enabled=true`.

Если пусто — один раз выполни:
```bash
python scripts/add_first_server.py
```
(после этого снова проверь выборку из `servers`.)

---

## 5. Записывается ли пользователь в Xray после оплаты

После успешной оплаты бот должен:
1. Выбрать сервер из `servers`
2. Сгенерировать UUID
3. Вызвать gRPC AddUser на 103.137.251.165
4. Сохранить подписку с `uuid` и `server_id`

**Проверка:**

1. Сделай тестовую оплату (или используй уже прошедшую).
2. На krotray.ru посмотри логи:
   ```bash
   journalctl -u krotray -n 200 --no-pager | grep -E "Xray|AddUser|subscription|uuid"
   ```
   Ожидаемо: строка вроде `Xray AddUser ok: user_id=... server_id=... uuid=...`. Если есть `Xray AddUser failed` или `No enabled server` — смотри пункты 1–4.
3. В БД проверь подписку:
   ```bash
   sudo -u postgres psql -d krotray -c "SELECT id, user_id, status, uuid, server_id, expires_at FROM subscriptions ORDER BY id DESC LIMIT 5;"
   ```
   У последней подписки после оплаты должны быть `uuid` (не пусто) и `server_id` (число).
4. На сервере 103.137.251.165 можно посмотреть пользователей inbound (если в Xray есть API/команда вывода пользователей по тегу) — там должен появиться новый UUID с email `user_<user_id>`.

Если AddUser в логах «ok», в `subscriptions` есть `uuid` и `server_id` — пользователь записывается в Xray.

---

## 6. Выдаётся ли VLESS-ключ в Mini App

При активной подписке с `uuid` пользователь должен видеть полную VLESS-ссылку и кнопку «Скопировать».

**Проверка:**

1. Открой бота в Telegram → «Личный кабинет» (Mini App).
2. Если подписка активна — в поле «Ключ доступа» должна быть **полная ссылка** вида `vless://xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx@103.137.251.165:443?encryption=none&...`.
3. Нажми «Скопировать» — в буфер должна попасть эта же ссылка.
4. Опционально: вызови API с сервера:
   ```bash
   curl -s -H "X-Telegram-Init-Data: <initData из браузера/приложения>" "https://krotray.ru/api/me"
   ```
   В ответе у активной подписки должно быть поле `vless_url` с полной ссылкой.

Если в Mini App показывается полная ссылка и копируется — выдача ключа работает.

---

## 7. Отключаются ли просроченные (RemoveUser и status=expired)

Каждые 5 минут фоновая задача ищет подписки с `status=active` и `expires_at < now()`, вызывает RemoveUser в Xray и ставит `status=expired`.

**Проверка:**

1. В БД создай подписку с истёкшим сроком (для теста):
   ```bash
   sudo -u postgres psql -d krotray -c "UPDATE subscriptions SET expires_at = now() - interval '1 day' WHERE id = (SELECT id FROM subscriptions WHERE status = 'active' LIMIT 1);"
   ```
2. Подожди до 5 минут (или перезапусти бота, чтобы задача скорее отработала).
3. Логи:
   ```bash
   journalctl -u krotray -n 100 --no-pager | grep -E "Expired|RemoveUser|disabled"
   ```
   Ожидаемо: сообщение вроде `Expired job: user_id=... subscription_id=... disabled`.
4. БД:
   ```bash
   sudo -u postgres psql -d krotray -c "SELECT id, user_id, status, expires_at FROM subscriptions ORDER BY id DESC LIMIT 5;"
   ```
   У той подписки должен быть `status=expired`.
5. На 103.137.251.165 (если есть способ посмотреть пользователей inbound) — пользователь с этим email должен исчезнуть.

Если в логах есть «disabled», в БД `status=expired` и в Xray пользователя нет — отключение просроченных работает.

---

## 8. Краткая сводка

| Шаг | Что проверить |
|-----|----------------|
| 1.1 | В конфиге Xray есть API и inbound для API, порт известен → это XRAY_GRPC_PORT. |
| 1.2 | Тег VLESS inbound из конфига = XRAY_INBOUND_TAG в .env. |
| 2 | С krotray.ru доступен 103.137.251.165:XRAY_GRPC_PORT (`nc -zv`). |
| 3 | В .env на krotray.ru заданы XRAY_*, VLESS_URL_TEMPLATE с `{uuid}`. |
| 4 | В БД есть запись в `servers` (host, grpc_port, enabled). |
| 5 | После оплаты в логах «AddUser ok», в subscriptions есть uuid и server_id. |
| 6 | В Mini App показывается полная VLESS-ссылка, кнопка «Скопировать» работает. |
| 7 | После истечения срока в логах «Expired job: ... disabled», в БД status=expired, в Xray пользователь удалён. |

Если все пункты выполнены — цепочка «оплата → запись юзера в Xray → выдача ключа → отключение просроченных» работает. Если что-то не сходится — пришли фрагмент конфига Xray (api + один VLESS inbound) и вывод команд из шагов 2, 4, 5 — подскажем, что именно поправить.
