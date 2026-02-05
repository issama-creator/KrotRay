# Полная инструкция: добавление нового Xray-сервера

Один документ — всё по шагам: от установки Xray на новом сервере до записи в БД на krotray.ru. Бэкенд сам выбирает **наименее загруженный** сервер при каждой новой оплате.

---

## Что нужно перед началом

- **Новый VPS** с root/доступом по SSH (IP или домен).
- **krotray.ru** — бот и БД уже работают, первый сервер (103.137.251.165) уже добавлен.
- Из репозитория понадобятся: `docs/xray_vars.example.json`, `scripts/gen_xray_config.py`.

---

# Часть 1: Новый сервер (где ставишь Xray)

## Шаг 1.1. Установить Xray

Подключись по SSH к **новому** серверу и установи Xray (официальный скрипт или вручную):

```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

Проверь:

```bash
/usr/local/bin/xray version
```

---

## Шаг 1.2. Сгенерировать ключи Reality (для нового сервера)

На **новом** сервере:

```bash
/usr/local/bin/xray x25519
```

Вывод будет примерно таким:
```
Private key: ICB2VEABWtA7cvfh100WfSVHqh4fZK6yXtEqj5lyukQ
Public key: OgH3-UkoJbWUhmz_bTPmUbRQbAOyRhIgQ841KI4C42w
```

- **Private key** — в конфиг Xray (в `xray_vars.json` → `private_key`).
- **Public key** — в VLESS-ссылку для клиентов (в шаблон на krotray.ru → `pbk=...`).

**Short ID** — 2–16 hex-символов, например `568d2499`. Можно оставить этот или сгенерировать свой (например `openssl rand -hex 4`).

---

## Шаг 1.3. Файл переменных и генерация конфига

На **новом** сервере создай каталог (например в домашней папке) и скопируй туда два файла из репозитория:

- `docs/xray_vars.example.json` → сохрани как `xray_vars.json`
- `scripts/gen_xray_config.py`

Открой **только** `xray_vars.json` и заполни поля (подставь свои значения):

```json
{
  "api_port": 8081,
  "vless_port": 443,
  "private_key": "СЮДА_ПРИВАТНЫЙ_КЛЮЧ_ИЗ_xray_x25519",
  "short_id": "568d2499",
  "first_client_uuid": "c8e59e9b-7d1f-424f-9440-e464b2a9fdd1"
}
```

- `api_port` — порт gRPC API (8081 или другой свободный).
- `vless_port` — порт VLESS (обычно 443).
- `private_key` — из вывода `xray x25519` (Private key).
- `short_id` — shortId Reality (например `568d2499`).
- `first_client_uuid` — любой UUID, можно не менять.

Сгенерируй полный конфиг и положи его в каталог Xray:

```bash
python3 gen_xray_config.py xray_vars.json > /usr/local/etc/xray/config.json
```

---

## Шаг 1.4. Проверка конфига и запуск Xray

```bash
/usr/local/bin/xray -test -config /usr/local/etc/xray/config.json
```

Должно быть: **Configuration OK.**

```bash
systemctl restart xray
systemctl enable xray
```

Проверь, что порты слушаются:

```bash
ss -tlnp | grep -E "443|8081"
```

Должны быть строки с **xray** на 443 и 8081, причём 8081 — на **0.0.0.0** (или `*:8081`).

---

## Шаг 1.5. Файрвол (если включён)

Если на новом сервере используется UFW:

```bash
ufw allow 443/tcp
ufw allow 8081/tcp
ufw reload
ufw status
```

Если файрвол не используется — порты и так доступны.

---

## Шаг 1.6. Запомнить данные для krotray.ru

Для части 2 понадобятся:

- **IP или домен** нового сервера (например `5.6.7.8`).
- **Порт gRPC API** (тот же, что в `api_port`, например 8081).
- **Публичный ключ Reality** (Public key из `xray x25519`).
- **Short ID** (тот же, что в `short_id` в `xray_vars.json`).

---

# Часть 2: krotray.ru (бот и БД)

Подключись по SSH к **krotray.ru** (сервер с ботом и PostgreSQL).

---

## Шаг 2.1. Собрать VLESS-шаблон для нового сервера

Шаблон — одна строка, в ней обязательно **{uuid}** (его подставит бот). Остальные параметры — под **новый** сервер (host, port, pbk, sid).

Формат (подставь **IP_НОВОГО**, **PUBLIC_KEY**, **SHORT_ID**):

```
vless://{uuid}@IP_НОВОГО:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.apple.com&fp=chrome&pbk=PUBLIC_KEY&sid=SHORT_ID&type=tcp#KrotRay
```

Пример для сервера 5.6.7.8:

```
vless://{uuid}@5.6.7.8:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.apple.com&fp=chrome&pbk=OgH3-UkoJbWUhmz_bTPmUbRQbAOyRhIgQ841KI4C42w&sid=568d2499&type=tcp#KrotRay
```

Эту строку используй ниже как `vless_url_template`.

---

## Шаг 2.2. Добавить сервер в БД

Выбери один из способов.

### Вариант A: через .env и скрипт

1. Открой .env:
   ```bash
   nano /opt/krotray/.env
   ```

2. Временно замени переменные на данные **нового** сервера (подставь свои значения):
   ```env
   XRAY_SERVER_NAME=Server2
   XRAY_SERVER_HOST=5.6.7.8
   XRAY_GRPC_PORT=8081
   XRAY_MAX_USERS=100
   VLESS_URL_TEMPLATE=vless://{uuid}@5.6.7.8:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.apple.com&fp=chrome&pbk=ТВОЙ_PUBLIC_KEY&sid=ТВОЙ_SHORT_ID&type=tcp#KrotRay
   ```
   Строка `VLESS_URL_TEMPLATE` — одна, без переносов. Сохрани (Ctrl+O, Enter, Ctrl+X).

3. Запусти скрипт:
   ```bash
   cd /opt/krotray
   source venv/bin/activate
   python scripts/add_first_server.py
   ```
   Ожидаемо: `Добавлен сервер: Server2 5.6.7.8:8081 (max_users=100)`.

4. При необходимости верни в .env значения для первого сервера (103.137.251.165), чтобы не путаться при следующем добавлении.

### Вариант B: через SQL

Одна команда (подставь имя, IP, порт, полный шаблон VLESS с **{uuid}**):

```bash
sudo -u postgres psql -d krotray -c "
INSERT INTO servers (name, host, grpc_port, active_users, max_users, enabled, vless_url_template)
VALUES (
  'Server2',
  '5.6.7.8',
  8081,
  0,
  100,
  true,
  'vless://{uuid}@5.6.7.8:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.apple.com&fp=chrome&pbk=ТВОЙ_PUBLIC_KEY&sid=ТВОЙ_SHORT_ID&type=tcp#KrotRay'
);
"
```

Строка `vless_url_template` — одна, без переносов внутри кавычек.

---

## Шаг 2.3. Проверить запись в БД

```bash
sudo -u postgres psql -d krotray -c "SELECT id, name, host, grpc_port, active_users, max_users, enabled FROM servers ORDER BY id;"
```

Должна появиться новая строка с твоим именем, host и портом.

---

## Шаг 2.4. Проверить доступ к gRPC с krotray.ru

На **krotray.ru** (подставь IP и порт нового сервера):

```bash
nc -zv 5.6.7.8 8081
```

Должно быть: **Connection to 5.6.7.8 8081 port [tcp/...] succeeded!**

Если **Connection refused** или таймаут — на новом сервере проверь: Xray слушает 8081 на 0.0.0.0, файрвол открыт.

---

## Шаг 2.5. Перезапуск бота

Не обязателен: новые строки в `servers` подхватываются при следующей оплате. Перезапуск нужен только если менял код или .env:

```bash
systemctl restart krotray
```

---

# Часть 3: Как выбирается сервер при оплате

- При **новой** подписке (не продление) бэкенд вызывает **get_least_loaded_server(db)**.
- Выбирается один сервер: **enabled = true**, **active_users < max_users**, сортировка по **active_users** по возрастанию, берётся первый.
- Итог: при каждой новой оплате берётся **наименее загруженный** из доступных серверов.
- Пользователь добавляется в Xray на этом сервере (AddUser), подписке проставляются **server_id** и **uuid**, ключ выдаётся по **vless_url_template** этого сервера.

При **продлении** подписки сервер не меняется — пользователь остаётся на том же сервере.

---

# Полный чек-лист на каждый новый сервер

| № | Где | Действие |
|---|-----|----------|
| 1 | Новый сервер | Установить Xray (`install-release.sh`). |
| 2 | Новый сервер | Выполнить `xray x25519`, сохранить Private key и Public key. |
| 3 | Новый сервер | Скопировать `xray_vars.example.json` → `xray_vars.json`, `gen_xray_config.py`. |
| 4 | Новый сервер | Заполнить в `xray_vars.json`: `api_port`, `vless_port`, `private_key`, `short_id`, `first_client_uuid`. |
| 5 | Новый сервер | Выполнить: `python3 gen_xray_config.py xray_vars.json > /usr/local/etc/xray/config.json`. |
| 6 | Новый сервер | Проверить: `xray -test -config ...`, перезапустить Xray, проверить порты (`ss -tlnp`), открыть 443 и 8081 в файрволе при необходимости. |
| 7 | krotray.ru | Собрать VLESS-шаблон с {uuid} для нового сервера (host, pbk, sid). |
| 8 | krotray.ru | Добавить сервер в БД: через .env + `python scripts/add_first_server.py` или через `INSERT INTO servers (...)`. |
| 9 | krotray.ru | Проверить: `SELECT ... FROM servers;` и `nc -zv НОВЫЙ_IP 8081`. |

После этого новый сервер участвует в выборе, и наименее загруженный будет выбираться автоматически при каждой новой оплате.
