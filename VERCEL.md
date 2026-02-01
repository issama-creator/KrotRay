# Деплой на Vercel

## 1. API (FastAPI)

API можно задеплоить на Vercel как отдельный проект.

### Шаги

1. **Создайте проект в Vercel** — New Project → Import из GitHub.
2. **Root Directory** — корень репозитория (всё в одном проекте).
3. **Framework Preset** — Other (или FastAPI, если есть).
4. **Environment Variables** — добавьте в Vercel:
   - `BOT_TOKEN` — токен бота
   - `DATABASE_URL` — **PostgreSQL** (SQLite на Vercel не поддерживается)
     - Бесплатно: [Neon](https://neon.tech), [Supabase](https://supabase.com)
     - Пример: `postgresql://user:pass@host/db?sslmode=require`
   - `MINI_APP_URL` — URL Mini App (например `https://krot-ray.vercel.app`)
   - `API_URL` — **URL самого API** после деплоя (например `https://krot-ray-api.vercel.app`)

5. **Deploy** — Vercel соберёт проект, API будет доступен по `https://<project>.vercel.app/api/me`.

### Миграции БД

После создания PostgreSQL подключитесь и выполните:

```bash
py -m alembic upgrade head
```

Можно запустить локально с `DATABASE_URL` от Neon/Supabase.

---

## 2. Mini App

Mini App — статический сайт. Варианты:

**Вариант A.** Отдельный проект Vercel, Root Directory = `mini_app`.

**Вариант B.** Один проект с API — положите содержимое `mini_app` в `public/`. Тогда:
- `https://<project>.vercel.app/` — Mini App
- `https://<project>.vercel.app/api/me` — API

Для варианта B нужно скопировать `mini_app/*` в `public/` и настроить маршрутизацию.

---

## 3. Бот

Бот работает через **long-polling** и не может работать как serverless. Его нужно запускать отдельно:

- локально: `py main.py`
- или на Railway / Render / VPS

В `.env` бота:

```
BOT_TOKEN=...
MINI_APP_URL=https://krot-ray.vercel.app
API_URL=https://krot-ray-api.vercel.app
```

Кнопка «Личный кабинет» открывает `MINI_APP_URL?api=API_URL`, поэтому Mini App всегда знает, куда ходить за данными.

---

## Рекомендуемая схема

| Компонент  | Где запускать              | URL                              |
|-----------|----------------------------|-----------------------------------|
| API       | Vercel                     | `https://krot-ray-api.vercel.app` |
| Mini App  | Vercel (отдельный проект)  | `https://krot-ray.vercel.app`     |
| Бот       | Локально / Railway         | —                                 |
| БД        | Neon / Supabase            | —                                 |
