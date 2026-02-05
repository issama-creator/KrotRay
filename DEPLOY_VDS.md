# Деплой на VDS FirstVDS — пошагово

Для VDS Прогрев: 1 CPU, 1 GB RAM, 15 GB SSD, Ubuntu 24.04.

---

## Шаг 0. Получить доступ к серверу

1. Зайди в [Личный кабинет FirstVDS](https://firstvds.ru/)
2. Найди свой сервер в списке
3. Узнай: **IP-адрес**, **логин** (root или другой), **пароль** (приходит на email или в панели)
4. Для подключения используй **SSH** или **консоль** в панели FirstVDS

---

## Шаг 1. Подключиться к серверу

**Вариант A — Windows (PowerShell или CMD):**
```bash
ssh root@ТВОЙ_IP
```
Подставь свой IP вместо `ТВОЙ_IP`. Введи пароль, когда попросит.

**Вариант B — консоль в браузере:**
- В панели FirstVDS: Серверы → твой сервер → Консоль
- Войди под root с паролем

---

## Шаг 2. Обновить систему

```bash
apt update && apt upgrade -y
```

---

## Шаг 3. Установить Python 3.11+

```bash
apt install -y python3 python3-pip python3-venv
python3 --version
```
Должно быть 3.10 или выше.

---

## Шаг 4. Установить PostgreSQL

```bash
apt install -y postgresql postgresql-contrib
systemctl enable postgresql
systemctl start postgresql
```

---

## Шаг 5. Создать базу данных

```bash
sudo -u postgres psql
```

В консоли PostgreSQL выполни:

```sql
CREATE USER krot WITH PASSWORD 'assaasin06';
CREATE DATABASE krotray OWNER krot;
\q
```

Замени `придумай_пароль` на свой пароль (запомни его).

---

## Шаг 6. Установить nginx

```bash
apt install -y nginx
systemctl enable nginx
systemctl start nginx
```

---

## Шаг 7. Склонировать проект

```bash
cd /opt
git clone https://github.com/ТВОЙ_ЮЗЕР/ТВОЙ_РЕПОЗИТОРИЙ.git krotray
cd krotray
```

**Если репозиторий приватный** — нужен токен или SSH-ключ.  
**Если проекта нет в GitHub** — залей вручную через `scp`:

На своём компьютере (в папке проекта):
```bash
scp -r . root@ТВОЙ_IP:/opt/krotray/
```

---

## Шаг 8. Создать виртуальное окружение и зависимости

```bash
cd /opt/krotray
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Шаг 9. Создать .env

```bash
nano .env
```

Вставь (замени значения на свои):

```env
BOT_TOKEN=твой_токен_от_BotFather
MINI_APP_URL=https://krot-ray.vercel.app
API_URL=https://ТВОЙ_IP
DATABASE_URL=postgresql://krotray:придумай_пароль@localhost:5432/krotray
```

Сохрани: `Ctrl+O`, Enter, `Ctrl+X`.

---

## Шаг 10. Выполнить миграции

```bash
source venv/bin/activate
alembic upgrade head
```

---

## Шаг 11. Проверить запуск

```bash
source venv/bin/activate
python main.py
```

Должен запуститься бот и API. Проверь в браузере: `http://ТВОЙ_IP:8000` — должен открыться JSON `{"status": "ok"}`.  
Останови: `Ctrl+C`.

---

## Шаг 12. Настроить systemd (автозапуск)

```bash
nano /etc/systemd/system/krotray.service
```

Вставь:

```ini
[Unit]
Description=KrotRay Bot + API
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/krotray
Environment="PATH=/opt/krotray/venv/bin"
ExecStart=/opt/krotray/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Сохрани и включи:

```bash
systemctl daemon-reload
systemctl enable krotray
systemctl start krotray
systemctl status krotray
```

---

## Шаг 13. Настроить nginx (проксирование и HTTPS)

**A) Пока без домена (только по IP):**

```bash
nano /etc/nginx/sites-available/krotray
```

Вставь:

```nginx
server {
    listen 80;
    server_name ТВОЙ_IP;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Включи:

```bash
ln -s /etc/nginx/sites-available/krotray /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
```

API будет доступен по `http://ТВОЙ_IP` (порт 80).

**B) Если есть домен (HTTPS):**

1. Укажи A-запись домена на IP сервера
2. Установи certbot: `apt install -y certbot python3-certbot-nginx`
3. Получи сертификат: `certbot --nginx -d твой-домен.ru`
4. В `.env` поменяй `API_URL=https://твой-домен.ru`

---

## Шаг 14. Обновить .env в боте

В `.env` на сервере:

```env
API_URL=https://ТВОЙ_IP
```

или, если настроил домен:

```env
API_URL=https://твой-домен.ru
```

Перезапусти сервис:

```bash
systemctl restart krotray
```

---

## Шаг 15. Настроить кнопку в BotFather

Кнопка «Личный кабинет» открывает Mini App с параметром `?api=...`.  
URL берётся из `MINI_APP_URL` и `API_URL` в коде бота. Ты передаёшь их в `get_main_keyboard()`, значит URL формируется автоматически. Проверь, что в `.env` на сервере `API_URL` совпадает с тем, по которому доступен API (IP или домен).

---

## Проверка

1. Открой бота в Telegram → /start
2. Нажми «Личный кабинет» — должен открыться Mini App
3. Mini App должен показать «Ключ не активен» или «Загрузка...» — данные идут с API
4. API: `http://ТВОЙ_IP/` или `http://ТВОЙ_IP/docs` — должен отвечать

---

## Полезные команды

| Действие | Команда |
|----------|---------|
| Статус | `systemctl status krotray` |
| Логи | `journalctl -u krotray -f` |
| Перезапуск | `systemctl restart krotray` |
| Остановить | `systemctl stop krotray` |

---

## Важно про HTTPS

Без домена и HTTPS Telegram может ругаться при открытии Mini App. Если что-то не открывается — заведи домен и настрой certbot (шаг 13B).

---

## Домен krotray.ru: проверка DNS и настройка HTTPS (пошагово)

### Шаг A. Проверка DNS с сервера

Подключись по SSH к VDS и выполни:

**1. Пинг по домену (3 пакета):**
```bash
ping -c 3 krotray.ru
```

- Если в ответе видишь `188.120.232.104` и `0% packet loss` — DNS уже указывает на твой сервер, переходи к шагу B.
- Если `Unknown host` или другой IP — переходи к шагу A2.

**2. Проверка через nslookup:**
```bash
nslookup krotray.ru
```

В блоке `Answer` должно быть:
```
Name:    krotray.ru
Address: 188.120.232.104
```

Если адрес другой или запись пустая — DNS ещё не обновился или A-запись в Бегете не сохранена.

**3. Проверка через Google DNS (важно для certbot):**  
Let's Encrypt резолвит домен через публичные DNS. Проверь с сервера:
```bash
nslookup krotray.ru 8.8.8.8
```
В ответе должно быть `Address: 188.120.232.104`. Если видишь `NXDOMAIN` — глобальная пропагация ещё не закончилась, certbot выдаст ошибку. Подожди 15–60 минут и повтори.

**4. Если DNS не резолвится:**
- Подожди 15–30 минут и повтори `ping -c 3 krotray.ru` и `nslookup krotray.ru 8.8.8.8`.
- Зайди в Бегет → домен krotray.ru → «Зона DNS» / «Записи DNS» и проверь: есть ли A-запись для **@** (корень) или для **krotray.ru** с IP **188.120.232.104**. Если нет — добавь и нажми «Сохранить».

---

### Шаг B. Установка certbot и настройка nginx

Выполняй **на сервере** по SSH (все команды по порядку).

**1. Установить certbot:**
```bash
apt update
apt install -y certbot python3-certbot-nginx
```

**2. Создать конфиг nginx:**
```bash
nano /etc/nginx/sites-available/krotray
```

Вставь (целиком, без лишних пробелов в начале строк):
```nginx
server {
    listen 80;
    server_name krotray.ru;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Сохрани: **Ctrl+O**, Enter, **Ctrl+X**.

**3. Включить сайт и проверить nginx:**
```bash
ln -sf /etc/nginx/sites-available/krotray /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
```
Должно быть: `syntax is ok` и `test is successful`. Затем:
```bash
systemctl reload nginx
```

**4. Получить SSL-сертификат:**
```bash
certbot --nginx -d krotray.ru
```
- Введи email (для уведомлений от Let's Encrypt).
- Согласись с условиями: **Y**.
- На вопрос про рассылку — **Y** или **N** по желанию.
- На вопрос «Redirect HTTP to HTTPS» выбери **2** (Redirect), чтобы весь трафик шёл по HTTPS.

**5. Если certbot пишет, что не может проверить домен (NXDOMAIN и т.п.):**
- Убедись, что `nslookup krotray.ru 8.8.8.8` с сервера возвращает `188.120.232.104`. Пока там NXDOMAIN — certbot не выдаст сертификат.
- Проверь в Бегете, что A-запись сохранена.
- Подожди завершения пропагации DNS (до 24–48 часов, часто 15–60 минут) и запусти certbot снова: `certbot --nginx -d krotray.ru`.

---

### Шаг C. Обновить .env и перезапустить бота

**1. Открыть .env:**
```bash
nano /opt/krotray/.env
```

**2. Найти строку `API_URL=` и заменить на:**
```env
API_URL=https://krotray.ru
```
Остальные строки (BOT_TOKEN, MINI_APP_URL, DATABASE_URL) не трогай. Сохрани: **Ctrl+O**, Enter, **Ctrl+X**.

**3. Перезапустить сервис:**
```bash
systemctl restart krotray
```

---

### Шаг D. Проверка

1. В браузере открой **https://krotray.ru** — должен открыться ответ API (`{"status":"ok", "docs":"/docs"}`).
2. В Telegram отправь боту **/start**, нажми **«Личный кабинет»** — Mini App должен загрузить данные с API (статус «Ключ не активен» и т.д.).
3. На сервере проверь пользователей:  
   `sudo -u postgres psql -d krotray -c "SELECT * FROM users;"`  
   После захода в Mini App должны появиться строки.

---

## Если /api/me возвращает 401 и users пустая

1. **Обнови код на сервере** (важен фикс проверки initData в `api/auth.py`):
   ```bash
   cd /opt/krotray && git pull
   ```
   Если деплой не через git — открой `nano /opt/krotray/api/auth.py` и проверь блок `secret_key = hmac.new(...)`: первый аргумент должен быть `b"WebAppData"`, второй — `BOT_TOKEN.encode()` (по документации Telegram: ключ = WebAppData, сообщение = токен).

2. **Перезапусти и смотри логи:**
   ```bash
   systemctl restart krotray
   journalctl -u krotray -f
   ```
   В Telegram открой бота → «Личный кабинет». В логах появится одна из причин 401:
   - `initData отсутствует` — заголовок X-Telegram-Init-Data не доходит (Nginx/прокси).
   - `Неверный initData` — неверная подпись (проверь BOT_TOKEN в .env и фикс HMAC в auth.py) или устаревший auth_date (>24 ч).
   - `BOT_TOKEN не задан` — .env не загружен (запуск из /opt/krotray, в unit есть WorkingDirectory=/opt/krotray).

3. **Проверь .env на сервере:**  
   `grep -E "BOT_TOKEN|API_URL|DATABASE_URL" /opt/krotray/.env` — BOT_TOKEN не пустой, API_URL=https://krotray.ru, DATABASE_URL=postgresql://...

---

## Xray-сервер (Итерация 6.1): куда ставить и как добавить в бота

### Куда ставить Xray

- **Вариант A — Xray на том же VDS, что и бот (krotray.ru)**  
  Удобно: один сервер, всё в одном месте. Установи Xray (или панель 3X-UI / Marzban) на этот VDS, включи gRPC API в конфиге. В `.env` укажи `XRAY_SERVER_HOST=127.0.0.1` и порт gRPC из конфига Xray.

- **Вариант B — Xray на отдельном сервере**  
  Бот и БД остаются на krotray.ru, Xray — на другом VPS. С машины, где запущен бот, должен быть **сетевой доступ** до `host:grpc_port` (открытый порт, файрвол). В `.env` укажи `XRAY_SERVER_HOST=IP_или_домен_сервера_Xray` и порт gRPC.

**Переносить Xray на VDS бота не обязательно** — достаточно зарегистрировать уже работающий сервер в БД (см. ниже).

### Добавить первый сервер в таблицу `servers`

1. **Миграции уже выполнены** (после `alembic upgrade head` таблица `servers` есть).

2. **В `.env` на VDS с ботом** добавь (подставь свои значения):
   ```env
   XRAY_INBOUND_TAG=vless-in
   XRAY_SERVER_NAME=Main
   XRAY_SERVER_HOST=103.137.251.165
   XRAY_GRPC_PORT=8080
   XRAY_MAX_USERS=100
   ```
   - **Xray на отдельном сервере (103.137.251.165), бот на krotray.ru** — оставь `XRAY_SERVER_HOST=103.137.251.165`. Порт `XRAY_GRPC_PORT` возьми из конфига Xray (блок gRPC API, не порт VLESS/443). Тег inbound в конфиге Xray должен совпадать с `XRAY_INBOUND_TAG` (например `vless-in`).
   - Если Xray на этом же VDS — `XRAY_SERVER_HOST=127.0.0.1`, порт — из конфига Xray (блок gRPC API).

3. **Выполни скрипт один раз** (из корня проекта на VDS):
   ```bash
   cd /opt/krotray
   source venv/bin/activate
   python scripts/add_first_server.py
   ```
   В консоли должно появиться: `Добавлен сервер: Main 127.0.0.1:8080 (max_users=100)` (или твой name/host/port). Повторный запуск не создаст дубликат по одному и тому же host:port.

4. **Проверка в БД** (по желанию):
   ```bash
   sudo -u postgres psql -d krotray -c "SELECT id, name, host, grpc_port, active_users, max_users, enabled FROM servers;"
   ```

После этого при успешной оплате бэкенд будет выбирать этот сервер и создавать в нём клиента (через gRPC, если реализован вызов Xray API).

### Реальный вызов Xray gRPC (AddUser / RemoveUser)

В проекте уже реализован **реальный gRPC-клиент** Xray:

- В папке `proto_xray/` лежат минимальные proto (typed_message, user, vless account, command).
- Из них генерируются Python-модули в `api/xray_grpc_gen/` (команда ниже).
- В `api/xray_grpc.py`: `add_user_to_xray()` — добавляет UUID во inbound (AlterInbound + AddUserOperation), `remove_user_from_xray()` — удаляет по email (RemoveUserOperation).

**Регенерация proto** (если менял proto-файлы или после клонирования без сгенерированных файлов):

```bash
cd /opt/krotray
source venv/bin/activate
python -m grpc_tools.protoc -I proto_xray --python_out=api/xray_grpc_gen --grpc_python_out=api/xray_grpc_gen \
  proto_xray/common/serial/typed_message.proto \
  proto_xray/common/protocol/user.proto \
  proto_xray/proxy/vless/account.proto \
  proto_xray/app/proxyman/command/command.proto
```

**Важно:** в конфиге Xray на 103.137.251.165 должен быть включён **gRPC API** (inbounds с `sniffing` и настройками VLESS + отдельный API inbound с `grpcSettings` или через `stats`/API). Тег inbound для VLESS должен совпадать с `XRAY_INBOUND_TAG` (например `vless-in`). Порт gRPC API — тот, что указан в `XRAY_GRPC_PORT`.
