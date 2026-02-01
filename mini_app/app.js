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

  var selectedTariff = { months: 3, price: 250 };

  function render() {
    var noSubBlock = document.getElementById("no-sub-block");
    var hasSubBlock = document.getElementById("has-sub-block");
    var noKeyBlock = document.getElementById("no-key-block");
    var hasKeyBlock = document.getElementById("has-key-block");
    var paymentLoadingBlock = document.getElementById("payment-loading-block");
    var btnGetKey = document.getElementById("btn-get-key");

    noSubBlock.classList.toggle("hidden", STATE !== "NO_SUBSCRIPTION");
    hasSubBlock.classList.toggle("hidden", STATE === "NO_SUBSCRIPTION");
    noKeyBlock.classList.toggle("hidden", STATE === "ACTIVE" || STATE === "PAYMENT_PENDING");
    hasKeyBlock.classList.toggle("hidden", STATE !== "ACTIVE");
    paymentLoadingBlock.classList.toggle("hidden", STATE !== "PAYMENT_PENDING");

    if (STATE === "ACTIVE") {
      document.getElementById("status-value").textContent = "Активна";
      document.getElementById("status-value").className = "info-card__value status_active";
      document.getElementById("subscription-value").textContent = "01.05.2025 (MSK+3)";
      document.getElementById("tariff-value").textContent = "3 месяца";
      document.getElementById("days-value").textContent = "89";
      document.getElementById("key-input").value = "vless://uuid@example.com:443?encryption=none";
      document.getElementById("key-status").textContent = "Активен";
      document.getElementById("key-status").className = "key-status active";
    } else if (STATE === "EXPIRED") {
      document.getElementById("status-value").textContent = "Истекла";
      document.getElementById("status-value").className = "info-card__value status_expired";
      document.getElementById("subscription-value").textContent = "15.01.2025 (MSK+3)";
      document.getElementById("tariff-value").textContent = "3 месяца";
      document.getElementById("days-value").textContent = "0";
    }

    if (STATE === "NO_SUBSCRIPTION" || STATE === "EXPIRED") {
      btnGetKey.textContent = STATE === "EXPIRED" ? "Продлить подписку" : "Получить ключ";
    }
  }

  render();

  // Accordion — инструкции
  document.querySelectorAll(".accordion").forEach(function (btn) {
    btn.addEventListener("click", function () {
      tg.HapticFeedback && tg.HapticFeedback.selectionChanged();
      var target = btn.dataset.target;
      var content = document.getElementById("accordion-" + target);
      var isOpen = content.classList.contains("open");
      document.querySelectorAll(".accordion-content").forEach(function (c) {
        c.classList.remove("open");
      });
      document.querySelectorAll(".accordion").forEach(function (b) {
        b.classList.remove("open");
      });
      if (!isOpen) {
        content.classList.add("open");
        btn.classList.add("open");
      }
    });
  });

  // Выбор тарифа
  function setSelected(card) {
    document.querySelectorAll(".tariff-card").forEach(function (c) {
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

  // Получить ключ — переход на оплату (реальная оплата в Итерации 5)
  document.getElementById("btn-get-key").addEventListener("click", function () {
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

  // Показать QR (заглушка)
  document.getElementById("btn-qr").addEventListener("click", function () {
    tg.HapticFeedback && tg.HapticFeedback.impactOccurred("light");
    tg.showAlert && tg.showAlert("QR-код будет доступен при поддержке клиентом.");
  });
})();
