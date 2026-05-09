-- Полная замена servers на тестовый пул (10 мемных нод, TEST-NET 203.0.113.0/24).
-- Нужно для LB: >= 2 wifi и >= 2 bypass (enabled=true, kf_type заполнен).
--
-- После: init_redis_servers.py и при необходимости DEL по паттерну user:kf:* в Redis.
--
BEGIN;

UPDATE subscriptions SET server_id = NULL WHERE server_id IS NOT NULL;
UPDATE servers SET linked_server_id = NULL;
DELETE FROM servers;

ALTER SEQUENCE servers_id_seq RESTART WITH 1;

INSERT INTO servers (name, host, grpc_port, active_users, max_users, enabled, kf_type, plan)
VALUES
  ('ШлепаVPN-gigachad', '203.0.113.10', 8081, 0, 100, true, 'wifi', 'default'),
  ('котлетус-rex',      '203.0.113.11', 8081, 0, 100, true, 'wifi', 'default'),
  ('абобус-lite',       '203.0.113.12', 8081, 0, 100, true, 'wifi', 'default'),
  ('няшный-wifi',       '203.0.113.13', 8081, 0, 100, true, 'wifi', 'default'),
  ('рофлан-поминки',    '203.0.113.14', 8081, 0, 100, true, 'wifi', 'default'),
  ('обходчик-мем',      '203.0.113.15', 8081, 0, 100, true, 'bypass', 'default'),
  ('булочка-bypass',    '203.0.113.16', 8081, 0, 100, true, 'bypass', 'default'),
  ('чебупицца-tunnel',  '203.0.113.17', 8081, 0, 100, true, 'bypass', 'default'),
  ('чак-норрис-proxy',  '203.0.113.18', 8081, 0, 100, true, 'bypass', 'default'),
  ('vpn-крокодил',      '203.0.113.19', 8081, 0, 100, true, 'bypass', 'default');

COMMIT;
