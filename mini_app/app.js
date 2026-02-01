(function () {
  var tg = window.Telegram && window.Telegram.WebApp;
  if (!tg) return;

  tg.ready();
  tg.expand();

  if (tg.themeParams && tg.themeParams.bg_color) {
    tg.setHeaderColor(tg.themeParams.bg_color);
    tg.setBackgroundColor(tg.themeParams.bg_color);
  }

  // Авторизация через initData (итерация 2 — только наличие, проверка на backend в итерации 4)
  var initData = tg.initData || "";
  var hasInitData = initData.length > 0;

  // Mock-данные (заглушки)
  var mockStatus = hasInitData ? "Активен" : "Нет данных";
  var mockSubscription = hasInitData ? "До 01.04.2025" : "—";

  document.getElementById("status-value").textContent = mockStatus;
  document.getElementById("subscription-value").textContent = mockSubscription;

  // Заглушки кнопок
  document.getElementById("btn-pay").addEventListener("click", function () {
    tg.HapticFeedback && tg.HapticFeedback.impactOccurred("light");
    tg.showAlert && tg.showAlert("Оплата будет доступна в следующей версии.");
  });

  document.getElementById("btn-config").addEventListener("click", function () {
    tg.HapticFeedback && tg.HapticFeedback.impactOccurred("light");
    tg.showAlert && tg.showAlert("Получение конфига будет доступно в следующей версии.");
  });
})();
