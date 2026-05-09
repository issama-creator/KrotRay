-- Закрыть пробный период для строки users (триал = created_at + 3 дня по коду services/vpn_access.py).
-- Подписка subscription_expires_at и строки subscriptions не меняются.
-- Замени 1183 на нужный users.id (как account_id в /servers).

BEGIN;

UPDATE users
SET
  created_at = (NOW() AT TIME ZONE 'utc') - INTERVAL '400 days',
  updated_at = NOW() AT TIME ZONE 'utc'
WHERE id = 1183;

COMMIT;
