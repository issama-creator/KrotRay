# Связка Flutter VPN с бэкендом + заполнение `cp_servers`

## Часть A — промпт для Cursor (вставить в проект Flutter)

Скопируй блок ниже целиком в чат Cursor в **репозитории Flutter-приложения** (не в репозиторий бота).

---

```
Ты senior Flutter разработчик. Нужно связать VPN-клиент с существующим FastAPI бэкендом KrotRay.

Базовый URL API (прод): <ВСТАВЬ HTTPS_URL, например https://api.krotray.ru>
Локально для отладки можно http://10.0.2.2:8000 (Android эмулятор) или IP компа в LAN.

Эндпоинты бэкенда (без префикса /api для control plane):
- POST /register
  Body JSON: { "device_id": "<uuid строка>", "platform": "android" | "ios" }
  Ответ: { "subscription_until": "<ISO8601>" }

- POST /attach-telegram
  Body JSON: { "device_id": "<тот же uuid>", "telegram_id": <int> }
  Ответ: { "ok": true, "subscription_until": "<ISO8601>" }
  telegram_id — числовой id пользователя Telegram (не username).

- GET /subscription?device_id=<uuid>
  Ответ: { "subscription_until", "days_left", "has_access", "tunnel_last_seen_at", "tunnel_likely_active" }

- POST /vpn-heartbeat (опционально)
  Body: { "device_id": "<uuid>", "connected": true | false }
  Для метки «примерно онлайн» в подписке; на выбор серверов в /config не влияет.

- GET /config?device_id=<uuid>
  Успех 200: JSON конфигурации для VPN (outbounds, meta) — формат не менять.
  403: подписка истекла — показать экран оплаты / открыть бота.
  404: устройство не найдено.
  503: JSON { "error": "no available servers" } — нет свободных bridge/NL по лимитам.

Требования:
1) При первом запуске сгенерировать UUID v4, сохранить в flutter_secure_storage как device_id.
2) Сразу после первого сохранения вызвать POST /register с platform из Platform.isAndroid / iOS.
3) Сохранить subscription_until локально (SharedPreferences или secure_storage) для UI.
4) После авторизации в Telegram или при переходе из бота вызвать POST /attach-telegram с telegram_id (получить через Telegram Login / deep link / передачу из бота — уточни у продукта; минимум — ручной ввод int для отладки).
5) Кнопка «Подключить»: GET /config?device_id=...; при 403 показать «Доступ истёк» и кнопку открытия бота; при 200 передать тело ответа в существующий вызов flutter_vless (или адаптировать под формат ответа).
6) Экран статуса: периодически или при возврате в приложение вызывать GET /subscription для отображения дней.
7) Вынести baseUrl в конфиг (dart-define, flavor или .env через flutter_dotenv).
8) Использовать package:http или dio; таймауты 15–30 с; логировать ошибки.

Не хранить и не показывать пользователю VLESS-строку вручную — только ответ /config.
```

---

Замени `<ВСТАВЬ HTTPS_URL>` на реальный домен API перед отправкой промпта.

---

## Часть B — миграции БД на сервере

### 1. Переменные окружения на машине, где крутится API

Файл `.env` (или переменные в панели хостинга):

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME
```

Для Alembic должен быть **тот же** `DATABASE_URL`, что и у процесса uvicorn/FastAPI.

### 2. Установка зависимостей (если ещё не стоят)

```bash
cd /path/to/KrotRay-Toonel-bot
pip install -r requirements.txt
```

### 3. Прогон миграций

```bash
alembic upgrade head
```

Проверка: в PostgreSQL должны существовать таблицы `cp_users`, `devices`, `cp_servers` (цепочка миграций до `head`, включая поля для heartbeat на `devices`, если прогонял свежий код).

Если Alembic ругается на ревизию — смотри `alembic_version` в БД и цепочку в `alembic/versions/`.

### 4. Проверка API

```bash
curl -s https://ТВОЙ_ДОМЕН/
```

Ожидается JSON вроде `{"status":"ok","docs":"/docs"}`.

Открой в браузере `https://ТВОЙ_ДОМЕН/docs` — должны быть видны `POST /register`, `GET /config`, и т.д.

---

## Часть C — добавить реальные сервера в `cp_servers`

Нужны **минимум**:

- хотя бы **один** узел с ролью **`nl`** (выход в Нидерландах);
- хотя бы **один** с ролью **`standard_bridge`** (обычный мост).

Для тарифа bypass позже — **`bypass_bridge`**.

Поля берутся из твоей Reality/VLESS-конфигурации на сервере:

| Поле | Смысл |
|------|--------|
| `ip` | IP или hostname, до которого клиент стучится по TCP 443 |
| `role` | `nl` \| `standard_bridge` \| `bypass_bridge` |
| `public_key` | публичный ключ Reality (pbk) |
| `short_id` | shortId |
| `sni` | serverName / SNI |
| `path` | обычно `/` или как в конфиге |
| `max_users` | верхняя граница для `current_users` при балансировке (см. часть F) |

### Способ 1 — скрипт (на сервере с кодом бота и тем же `.env`)

```bash
cd /path/to/KrotRay-Toonel-bot

# Пример: NL
python scripts/add_cp_server.py --ip 203.0.113.10 --role nl --public-key "ВАШ_pbk" --short-id "ВАШ_sid" --sni www.example.com --path / --max-users 200

# Пример: мост Москва
python scripts/add_cp_server.py --ip 198.51.100.20 --role standard_bridge --public-key "ВАШ_pbk" --short-id "ВАШ_sid" --sni www.other.com --path / --max-users 150
```

Повтори для каждого физического узла (можно несколько `nl` и несколько `standard_bridge` — см. балансировку в части F).

### Способ 2 — SQL в PostgreSQL (если нет Python под рукой)

```sql
INSERT INTO cp_servers (ip, role, public_key, short_id, sni, path, max_users, current_users, latency, active, created_at)
VALUES
  ('203.0.113.10', 'nl', 'PUBLIC_KEY_NL', 'shortid_nl', 'sni.example.com', '/', 200, 0, NULL, true, NOW()),
  ('198.51.100.20', 'standard_bridge', 'PUBLIC_KEY_BR', 'shortid_br', 'sni2.example.com', '/', 150, 0, NULL, true, NOW());
```

Имена колонок должны совпадать с миграцией `005` + `006` (без `max_users_base` после `006`).

### Health-воркер

Раз в 2 минуты бэк делает TCP `ip:443`. Если узел недоступен **3 раза подряд**, выставит `active = false` — такой узел **не попадёт** в `/config`. Убедись, что файрвол **разрешает** исходящие с API к этим IP:443 (если воркер крутится на том же хосте — обычно ок).

---

## Часть F — балансировка `cp_servers` (реализовано в FastAPI)

Схема **без** Xray stats и **без** изменения формата ответа `GET /config`. Узлы — строки в таблице **`cp_servers`** (поля `active`, `current_users`, `max_users`, `latency`).

1. **Выбор кандидатов (отдельно для bridge и для NL)**  
   - `active = true`, `max_users > 0`  
   - `current_users < max_users`  
   - **safety margin:** сырой load `(current_users * 1.0 / max_users) < 0.8` — запас, если счётчик неточный  
   - сортировка: по тому же отношению `current_users / max_users` по возрастанию, затем `latency ASC NULLS LAST`  
   - в коде: `LIMIT 3`, затем **случайный** один из этих трёх (anti-spike).  
   - `max_users` — технический потолок; ориентир по реальной нагрузке ~70–80% от него.

2. **После выбора** для каждого из двух узлов (bridge + NL): `current_users += 1` в той же транзакции, что и ответ `/config`.

3. **Decay-воркер** (`workers/cp_server_decay.py`): каждые **2 минуты** для всех `active = true`: уменьшить `current_users` на **5**, не ниже **0** (плавное «остывание» вместо полного сброса).

4. **503** если не нашлось bridge или NL: тело **`{"error": "no available servers"}`**.

5. **Логи** (временно): `server_id`, `current_users`, `max_users`, `load_percent`.

Константы в коде: `api/cp_api.py` (`_CP_LOAD_CAP` = 0.8, `_CP_TOP_K` = 3). Расписание decay: `api/main.py` (job `cp_server_decay`, интервал 2 минуты).

---

## Часть G — упрощённое ядро heartbeat + выбор пар (edge)

**Отдельно** от legacy `servers` и CP-таблицы `devices`: таблицы **`edge_servers`**, **`edge_devices`** (миграция `010`).

| Метод | Путь | Назначение |
|--------|------|------------|
| POST | `/ping` | `{ "device_id", "server_id" }` — upsert heartbeat; `server_id` только **exit** |
| POST | `/config` | JSON `{ "servers": [ { "exit": {id, host}, "bridge": {id, host} }, ... ] }` до **4** пар; exit с онлайн-нагрузкой **> 150** не предлагаются; из остальных — **топ 10** наименее загруженных → **random** до 4 → пары с bridge |

`GET /config` (VPN из `cp_servers`) **не трогается** — другой метод на том же пути.

Заполни `edge_servers`: `type` = `exit` \| `bridge`, одинаковый **`group_id`** у пары bridge+exit. Логика в `api/edge_lb_api.py` (сырой SQL через `db.execute(text(...))`).

**Нагрузочная симуляция (локально):** `scripts/simulate_edge_lb_load.py` — виртуальные `device_id`, `POST /config`, `POST /ping`; сводка по `server_id`. Сид **в консоль**: `--emit-seed-sql 100`. Сид **в БД с выводом SQL в консоль**: `DATABASE_URL=... python scripts/simulate_edge_lb_load.py --apply-seed 100`. Пайп: `--emit-seed-sql 100 | psql "$DATABASE_URL"`. Прогон: `--fast` для коротких пауз между пингами.

---

## Часть D — домен, HTTPS, Flutter

1. **Один публичный HTTPS URL** для API (reverse proxy nginx/caddy → uvicorn `127.0.0.1:8000`).
2. В **Flutter** в коде или конфиге указать именно этот URL (не `localhost` в релизной сборке).
3. В **Telegram BotFather** при необходимости обновить ссылки мини-аппа; `API_URL` / `MINI_APP_URL` в `.env` бота должны указывать на те же прод-домены, что ты реально используешь.
4. Android: для HTTPS используй валидный сертификат; для cleartext HTTP только отладка (`android:usesCleartextTraffic`).

---

## Часть E — быстрый чеклист «всё связано»

- [ ] `alembic upgrade head` на прод-БД  
- [ ] В `cp_servers` есть минимум 1× `nl` и 1× `standard_bridge`, `active=true`  
- [ ] `curl https://API/register` не обязателен; проще через `/docs` или Postman: `POST /register`  
- [ ] После регистрации `GET /config?device_id=...` возвращает 200 (не 503)  
- [ ] Flutter использует тот же `baseUrl`  
- [ ] После оплаты в мини-аппе у того же `telegram_id` вызывался `/attach-telegram` с `device_id` телефона — тогда дни подтянутся с аккаунта  

---

## Пример ручной проверки (Postman / curl)

Замени `BASE` и сгенерируй UUID.

```bash
export BASE=https://api.example.com
export DID=$(python -c "import uuid; print(uuid.uuid4())")

curl -s -X POST "$BASE/register" -H "Content-Type: application/json" \
  -d "{\"device_id\":\"$DID\",\"platform\":\"android\"}"

curl -s "$BASE/subscription?device_id=$DID"

curl -s "$BASE/config?device_id=$DID"
```

Если `/config` отдаёт **503** с `{"error":"no available servers"}` — нет подходящих bridge/NL в `cp_servers`, все `active=false`, упёрлись в `max_users` и/или порог **0.8** сырой загрузки.
