-- Edge LB diagnostics (PostgreSQL)
-- Usage:
--   psql "$DATABASE_URL" -f scripts/edge_diagnostics.sql

-- 1) Edge users summary
SELECT
    COUNT(*)::int AS total_users,
    COUNT(*) FILTER (WHERE is_active = true)::int AS active_users,
    COUNT(*) FILTER (WHERE is_active = false)::int AS inactive_users,
    COUNT(*) FILTER (WHERE expires_at <= NOW())::int AS expired_users
FROM edge_users;

-- 2) Expired keys (latest first)
SELECT
    id,
    device_id,
    key,
    is_active,
    expires_at
FROM edge_users
WHERE expires_at <= NOW()
ORDER BY expires_at DESC
LIMIT 50;

-- 3) Edge server inventory by type/activity
SELECT
    type,
    is_active,
    COUNT(*)::int AS n
FROM edge_servers
GROUP BY type, is_active
ORDER BY type, is_active DESC;

-- 4) Online load per exit for last 90 seconds (production metric)
WITH exit_load AS (
    SELECT
        s.id AS server_id,
        s.host,
        COALESCE(cnt.c, 0)::int AS load_90s
    FROM edge_servers s
    LEFT JOIN (
        SELECT
            d.server_id,
            COUNT(*)::int AS c
        FROM edge_devices d
        WHERE d.last_seen > NOW() - INTERVAL '90 seconds'
        GROUP BY d.server_id
    ) cnt ON cnt.server_id = s.id
    WHERE s.type = 'exit' AND s.is_active = true
)
SELECT
    server_id,
    host,
    load_90s
FROM exit_load
ORDER BY load_90s DESC, server_id
LIMIT 100;

-- 5) Distribution quality snapshot for active exits (90s window)
WITH exit_load AS (
    SELECT
        s.id AS server_id,
        COALESCE(cnt.c, 0)::int AS load_90s
    FROM edge_servers s
    LEFT JOIN (
        SELECT
            d.server_id,
            COUNT(*)::int AS c
        FROM edge_devices d
        WHERE d.last_seen > NOW() - INTERVAL '90 seconds'
        GROUP BY d.server_id
    ) cnt ON cnt.server_id = s.id
    WHERE s.type = 'exit' AND s.is_active = true
)
SELECT
    COUNT(*)::int AS active_exit_count,
    COALESCE(MIN(load_90s), 0)::int AS min_load_90s,
    COALESCE(MAX(load_90s), 0)::int AS max_load_90s,
    ROUND(COALESCE(AVG(load_90s), 0)::numeric, 2) AS avg_load_90s,
    ROUND(COALESCE(STDDEV_POP(load_90s), 0)::numeric, 2) AS stdev_load_90s
FROM exit_load;

-- 6) Stale devices (>180 sec without ping)
SELECT
    d.device_id,
    d.server_id,
    d.last_seen,
    EXTRACT(EPOCH FROM (NOW() - d.last_seen))::int AS seconds_since_seen
FROM edge_devices d
WHERE d.last_seen <= NOW() - INTERVAL '180 seconds'
ORDER BY d.last_seen ASC
LIMIT 100;

-- 7) Total devices tracked and currently online (90 sec)
SELECT
    (SELECT COUNT(*)::int FROM edge_devices) AS total_devices,
    (SELECT COUNT(*)::int FROM edge_devices WHERE last_seen > NOW() - INTERVAL '90 seconds') AS online_90s_devices;
