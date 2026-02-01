(function () {
  var tg = window.Telegram && window.Telegram.WebApp;
  if (!tg) return;

  tg.ready();
  tg.expand();

  if (tg.themeParams && tg.themeParams.bg_color) {
    tg.setHeaderColor(tg.themeParams.bg_color);
    tg.setBackgroundColor(tg.themeParams.bg_color);
  }

  var initData = tg.initData || "";
  var hasInitData = initData.length > 0;

  var mockStatus = hasInitData ? "Активен" : "Нет данных";
  var mockSubscription = hasInitData ? "01.04.2025" : "—";

  document.getElementById("status-value").textContent = mockStatus;
  document.getElementById("subscription-value").textContent = mockSubscription;

  // Выбор тарифа: 1 мес 100₽, 3 мес 300₽
  var selectedTariff = { months: 3, price: 250 };

  function setSelected(card) {
    var cards = document.querySelectorAll(".tariff-card");
    cards.forEach(function (c) {
      c.classList.remove("tariff-card_selected");
    });
    card.classList.add("tariff-card_selected");
    selectedTariff.months = parseInt(card.dataset.months, 10);
    selectedTariff.price = parseInt(card.dataset.price, 10);
  }

  document.getElementById("tariff-1").addEventListener("click", function () {
    tg.HapticFeedback && tg.HapticFeedback.selectionChanged();
    setSelected(this);
  });

  document.getElementById("tariff-3").addEventListener("click", function () {
    tg.HapticFeedback && tg.HapticFeedback.selectionChanged();
    setSelected(this);
  });

  // Получить ключ — переход на оплату (реальная оплата в итерации 5)
  document.getElementById("btn-get-key").addEventListener("click", function () {
    tg.HapticFeedback && tg.HapticFeedback.impactOccurred("medium");
    tg.showAlert &&
      tg.showAlert(
        "Тариф: " + selectedTariff.months + " мес, " + selectedTariff.price + " ₽. Оплата будет подключена в следующей версии."
      );
  });
})();
