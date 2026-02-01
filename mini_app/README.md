# Mini App — личный кабинет (Итерация 2)

Только UI, все данные — mock/stub.

## Деплой

Mini App должен открываться по **HTTPS**. Варианты:

1. **Vercel** — загрузите папку `mini_app` как проект (или корень репозитория с `mini_app` как root).
2. **Netlify** — то же: укажите папку `mini_app` как publish directory.
3. **GitHub Pages** — положите содержимое `mini_app` в ветку `gh-pages` или в папку `docs`.

После деплоя получите URL (например `https://your-app.vercel.app`). Этот URL пропишите в `.env` проекта как `MINI_APP_URL` и перезапустите бота.

## Локальный просмотр (без бота)

Из папки `mini_app`:

```bash
npx serve .
```

или

```bash
python -m http.server 8080
```

Откройте в браузере. В Telegram кнопка «Личный кабинет» откроет Mini App только по HTTPS (после деплоя).
