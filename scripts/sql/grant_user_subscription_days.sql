-- Имитация оплаты: платный доступ N дней через users.subscription_expires_at.
-- Триал в UI отключится (есть «оплата»). Замени id и интервал при необходимости.

BEGIN;

UPDATE users
SET
  subscription_expires_at = (NOW() AT TIME ZONE 'utc') + INTERVAL '15 days',
  updated_at = NOW() AT TIME ZONE 'utc'
WHERE id = 1183;

COMMIT;
