(function () {
  var tg = window.Telegram && window.Telegram.WebApp;
  if (!tg) return;

  tg.ready();
  tg.expand();

  if (tg.themeParams && tg.themeParams.bg_color) {
    tg.setHeaderColor(tg.themeParams.bg_color);
    tg.setBackgroundColor(tg.themeParams.bg_color);
  }

  // Состояния: NO_SUBSCRIPTION | ACTIVE | EXPIRED | PAYMENT_PENDING
  // Mock: по умолчанию нет подписки. Для превью добавить ?state=active в URL
  var params = new URLSearchParams(window.location.search);
  var stateParam = params.get("state");
  var STATE =
    stateParam === "active"
      ? "ACTIVE"
      : stateParam === "expired"
      ? "EXPIRED"
      : stateParam === "payment"
      ? "PAYMENT_PENDING"
      : "NO_SUBSCRIPTION";

  var selectedTariff = { months: 1, price: 100 };

  function render() {
    var statusText = document.getElementById("status-text");
    var hasKeyBlock = document.getElementById("has-key-block");
    var buySection = document.getElementById("buy-section");
    var btnBuyKey = document.getElementById("btn-buy-key");

    if (STATE === "ACTIVE") {
      statusText.textContent = "Активен до 01.05.2025";
      statusText.className = "status-text active";
      hasKeyBlock.classList.remove("hidden");
      buySection.classList.add("hidden");
      document.getElementById("key-input").value = "vless://uuid@example.com:443?encryption=none";
    } else if (STATE === "EXPIRED") {
      statusText.textContent = "Ключ истёк";
      statusText.className = "status-text";
      hasKeyBlock.classList.add("hidden");
      buySection.classList.remove("hidden");
      btnBuyKey.textContent = "Продлить подписку";
    } else if (STATE === "PAYMENT_PENDING") {
      statusText.textContent = "Оплата в процессе...";
      statusText.className = "status-text";
      hasKeyBlock.classList.add("hidden");
      buySection.classList.add("hidden");
    } else {
      statusText.textContent = "Ключ не активен";
      statusText.className = "status-text";
      hasKeyBlock.classList.add("hidden");
      buySection.classList.remove("hidden");
      btnBuyKey.textContent = "Купить ключ";
    }
  }

  render();

  // Выбор тарифа
  function setSelected(card) {
    document.querySelectorAll(".tariff-row").forEach(function (c) {
      c.classList.remove("tariff-row_selected");
    });
    card.classList.add("tariff-row_selected");
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

  // Купить ключ — переход на оплату (реальная оплата в Итерации 5)
  document.getElementById("btn-buy-key").addEventListener("click", function () {
    tg.HapticFeedback && tg.HapticFeedback.impactOccurred("medium");
    tg.showAlert &&
      tg.showAlert(
        "Тариф: " +
          selectedTariff.months +
          " мес, " +
          selectedTariff.price +
          " ₽. Оплата через ЮKassa будет подключена в Итерации 5."
      );
  });

  // Скопировать ключ
  document.getElementById("btn-copy").addEventListener("click", function () {
    tg.HapticFeedback && tg.HapticFeedback.notificationOccurred("success");
    var input = document.getElementById("key-input");
    input.select();
    input.setSelectionRange(0, 99999);
    try {
      navigator.clipboard.writeText(input.value);
      tg.showAlert && tg.showAlert("Ключ скопирован");
    } catch (e) {
      tg.showAlert && tg.showAlert("Скопируйте ключ вручную");
    }
  });

})();
