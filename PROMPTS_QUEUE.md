# PROMPTS QUEUE

Сюда добавляй промпты по одному блоку.
Я беру первый блок со статусом `NEW`, выполняю, потом отмечаю `DONE`.

## Правила заполнения

- Один промпт = один блок.
- Короткое название в `Title`.
- Основной текст в `Prompt`.
- Если есть важные ограничения, пиши в `Constraints`.

## Шаблон блока

```text
### [ID: 001] [Status: NEW]
Title: Краткое название
Prompt:
<текст промпта>
Constraints:
- <ограничение 1>
- <ограничение 2>
```

---

### [ID: 001] [Status: NEW]
Title: Первый промпт
Prompt:
<вставь сюда первый промпт>
Constraints:
- Безопасно
- Без удаления данных

🚀 PROMPT 1 — БД (ФИНАЛЬНАЯ СХЕМА)
Status: DONE
Ты senior backend инженер.

Создай PostgreSQL схему для VPN backend.

Таблицы:

1. servers:
- id SERIAL PRIMARY KEY
- host TEXT NOT NULL
- status TEXT DEFAULT 'alive'
- load FLOAT DEFAULT 0
- score FLOAT DEFAULT 0
- previous_active INT DEFAULT 0
- cooldown_until TIMESTAMP NULL
- updated_at TIMESTAMP DEFAULT NOW()

2. connections:
- key TEXT
- server_id INT
- last_seen TIMESTAMP
- PRIMARY KEY (key)

Индексы:

CREATE INDEX idx_connections_server_last_seen
ON connections(server_id, last_seen);

CREATE INDEX idx_connections_last_seen
ON connections(last_seen);

CREATE INDEX idx_servers_score
ON servers(score);

Код: чистый SQL, production-ready
🚀 PROMPT 2 — /PING ENDPOINT
Status: DONE
Ты senior backend инженер.

Реализуй FastAPI endpoint:

POST /ping

Вход:
- key
- server_id

Логика:

1. найти существующую запись
2. если last_seen < 30 сек → НЕ обновлять
3. иначе:
   - insert или update
   - last_seen = now()

Требования:
- upsert
- быстрый
- без лишней логики
🚀 PROMPT 3 — BATCH ACTIVE USERS
Status: DONE
Ты senior backend инженер.

Реализуй функцию:

get_active_users_map()

SQL:

SELECT server_id, COUNT(*) as active
FROM connections
WHERE last_seen > NOW() - INTERVAL '180 seconds'
GROUP BY server_id;

Вернуть:

dict:
{server_id: active}

Если сервера нет → считать 0

Python + SQL
🚀 PROMPT 4 — SCORE (БЕЗ PING)
Status: DONE
Ты senior backend инженер.

Реализуй функцию:

def calculate_score(load: float) -> float

Логика:

score = load ** 1.2

Без ping

Код чистый
🚀 PROMPT 5 — COOLDOWN (ФИКС)
Status: DONE
Ты senior backend инженер.

Реализуй:

def check_spike(active, previous_active, threshold=20) -> bool

def apply_cooldown(weight, cooldown_until, now) -> float

Логика:

если active - previous_active > threshold:
    cooldown_until = now + 10 сек

apply_cooldown:
если now < cooldown_until:
    weight *= 0.3

Важно:
- cooldown НЕ влияет на score
- только на weight
🚀 PROMPT 6 — WEIGHT
Status: DONE
Ты senior backend инженер.

Реализуй:

def calculate_weight(server, now):

Вход:
- score
- load
- cooldown_until

free_ratio = 1 - load

Формула:

base = 1 / (score + 0.01)
capacity = free_ratio ** 2

weight = base * capacity

применить cooldown

Вернуть weight
🚀 PROMPT 7 — FILTER + FALLBACK
Status: DONE
Ты senior backend инженер.

Реализуй:

get_candidate_servers()

1. взять топ 20 по score

2. фильтр:
- status = 'alive'
- load < 0.9
- free_ratio > 0.1

3. если <4:
→ fallback:
- взять топ 20
- random.sample(4)
- БЕЗ weight

4. если 0:
→ вернуть топ 4

Код чистый
🚀 PROMPT 8 — WEIGHTED RANDOM
Status: DONE
Ты senior backend инженер.

Реализуй:

weighted_sample(servers, k=4)

Логика:

- считаем weight
- random.choices
- без повторов
- если веса = 0 → random.sample

Код production-ready
🚀 PROMPT 9 — /CONFIG ENDPOINT
Status: DONE
Ты senior backend инженер.

Реализуй:

GET /config

Вход:
- key

Логика:

1. получить candidate servers
2. weighted_sample (4)
3. fallback если ошибка

Вернуть список серверов

Максимально быстрый endpoint
🚀 PROMPT 10 — WORKER (ФИНАЛ)
Status: DONE
Ты senior backend инженер.

Реализуй worker:

каждые 5 секунд:

1. получить все servers
2. получить active_map (GROUP BY)
3. для каждого:

active = dict.get(id, 0)
load = active / MAX_CONNECTIONS

score = load ** 1.2

если spike:
    cooldown_until = now + 10 сек

обновить:
- load
- score
- previous_active
- cooldown_until

4. batch update

Требования:
- минимум SQL
- без COUNT в цикле
- production-ready
🚀 PROMPT 11 — CLEANUP
Status: DONE
Ты senior backend инженер.

Добавь задачу:

каждые 5 минут:

DELETE FROM connections
WHERE last_seen < NOW() - INTERVAL '10 minutes';

Безопасно и эффективно
🧠 ЧТО У ТЕБЯ БУДЕТ ПОСЛЕ
✔ backend  
✔ worker  
✔ балансировка  
✔ анти-перегруз  
✔ fallback  
✔ стабильность  
⚡ СУПЕР КОРОТКО
это полный backend VPN системы  
💬 ЧЕСТНО

Если ты это соберёшь:

у тебя будет готовый прод уровень backend