# Что сделано и что делать на сервере с бэкендом (krotray.ru)

## Что сделано и что работает

| Часть | Что сделано | Что в итоге работает |
|-------|-------------|----------------------|
| **Оплата** | ЮKassa: создание платежа, webhook `payment.succeeded` | Пользователь платит → платёж подтверждается → подписка создаётся или продлевается (30/90 дней). |
| **Серверы** | Таблица `servers`, выбор наименее загруженного (`active_users` ↑) | При оплате бэкенд выбирает сервер с минимумом пользователей. |
| **Xray gRPC** | AddUser / RemoveUser через proto Xray | После оплаты UUID добавляется во inbound Xray на выбранном сервере. При истечении подписки — удаляется из Xray. |
| **VLESS-ключ** | Шаблон с `{uuid}`, GET /api/key, vless_url в /api/me | Пользователь видит полную VLESS-ссылку в Mini App и может её скопировать. |
| **Просроченные** | Фоновая задача раз в 5 минут | Подписки с `expires_at < now()` помечаются как expired, пользователь удаляется из Xray, `active_users` уменьшается. |
| **Несколько серверов** | Поле `vless_url_template` у каждого сервера | Можно 10–30 серверов: у каждого свой шаблон ссылки, ключ выдаётся по серверу подписки. |

---

## Что сделать на сервере с бэкендом (krotray.ru)

Подключись по SSH к **серверу, где крутится бот и API** (krotray.ru) и выполни по порядку.

### 1. Обновить код

Если деплой через git:

```bash
cd /opt/krotray
git pull
```

Если без git — скопируй обновлённые файлы (всю папку проекта) на сервер в `/opt/krotray` (или туда, где у тебя лежит бот).

---

### 2. Добавить переменные в .env

Открой .env:

```bash
nano /opt/krotray/.env
```

В конец файла добавь (подставь свои значения: порт gRPC и тег inbound из конфига Xray):

```env
# Xray
XRAY_INBOUND_TAG=vless-in
XRAY_SERVER_NAME=Main
XRAY_SERVER_HOST=103.137.251.165
XRAY_GRPC_PORT=8080
XRAY_MAX_USERS=100

# VLESS-ссылка (одной строкой, без переносов)
VLESS_URL_TEMPLATE=vless://{uuid}@103.137.251.165:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.apple.com&fp=chrome&pbk=OgH3-UkoJbWUhmz_bTPmUbRQbAOyRhIgQ841KI4C42w&sid=568d2499&type=tcp#KrotRay
```

Сохрани: **Ctrl+O**, Enter, **Ctrl+X**.

---

### 3. Установить зависимости

```bash
cd /opt/krotray
source venv/bin/activate
pip install -r requirements.txt
```

(Подтянутся grpcio, apscheduler, protobuf и т.д.)

---

### 4. Применить миграции БД

```bash
cd /opt/krotray
source venv/bin/activate
alembic upgrade head
```

(Добавится колонка `vless_url_template` в `servers`, если её ещё нет.)

---

### 5. Добавить первый Xray-сервер в БД (один раз)

```bash
cd /opt/krotray
source venv/bin/activate
python scripts/add_first_server.py
```

Должно вывести что-то вроде: `Добавлен сервер: Main 103.137.251.165:8080 (max_users=100)`.

---

### 6. Перезапустить бота и API

```bash
systemctl restart krotray
```

Проверка:

```bash
systemctl status krotray
journalctl -u krotray -n 30 --no-pager
```

Ошибок быть не должно.

---

## Краткий чек-лист

- [ ] `git pull` (или заливка кода)
- [ ] В `.env` добавлены XRAY_* и VLESS_URL_TEMPLATE
- [ ] `pip install -r requirements.txt`
- [ ] `alembic upgrade head`
- [ ] `python scripts/add_first_server.py`
- [ ] `systemctl restart krotray`

После этого изменения вступают в силу: при оплате будет выбираться сервер, создаваться пользователь в Xray, выдаваться VLESS-ключ, просроченные будут отключаться.
