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
CREATE USER krotray WITH PASSWORD 'придумай_пароль';
CREATE DATABASE krotray OWNER krotray;
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
