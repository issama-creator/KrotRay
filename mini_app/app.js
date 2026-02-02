(function () {
  var tg = window.Telegram && window.Telegram.WebApp;
  if (!tg) {
    tg = { initData: "", HapticFeedback: null, showAlert: function (m) { alert(m); } };
  } else {
    tg.ready();
    tg.expand();
  }

  if (tg.themeParams && tg.themeParams.bg_color) {
    tg.setHeaderColor(tg.themeParams.bg_color);
    tg.setBackgroundColor(tg.themeParams.bg_color);
  }

  var params = new URLSearchParams(window.location.search);
  var apiBase = params.get("api") || "http://localhost:8000";
  apiBase = apiBase.replace(/\/$/, "");

  var STATE = "NO_SUBSCRIPTION";
  var data = { subscription: null };

  var selectedTariff = { months: 1, price: 100 };

  function formatDate(isoStr) {
    if (!isoStr) return "";
    try {
      var d = new Date(isoStr);
      return d.toLocaleDateString("ru-RU", {
        day: "numeric",
        month: "long",
        year: "numeric",
      });
    } catch (e) {
      return isoStr;
    }
  }

  function daysLeft(expiresAt) {
    if (!expiresAt) return 0;
    var end = new Date(expiresAt);
    var now = new Date();
    var diff = end - now;
    return Math.max(0, Math.ceil(diff / (24 * 60 * 60 * 1000)));
  }

  function pluralDays(n) {
    if (n === 1) return "день";
    if (n >= 2 && n <= 4) return "дня";
    return "дней";
  }

  function showScreen(name) {
    var main = document.getElementById("screen-main");
    var tariffs = document.getElementById("screen-tariffs");
    if (main) main.classList.toggle("screen_hidden", name !== "main");
    if (tariffs) tariffs.classList.toggle("screen_hidden", name !== "tariffs");
  }

  function render() {
    var statusText = document.getElementById("status-text");
    var statusSubtitle = document.getElementById("status-subtitle");
    var statusPill = document.getElementById("status-pill");
    var statusPillText = document.getElementById("status-pill-text");
    var keyInput = document.getElementById("key-input");
    var btnBuyKeyTopText = document.getElementById("btn-buy-key-top-text");

    function setBuyButtonLabel(label) {
      if (btnBuyKeyTopText) btnBuyKeyTopText.textContent = label;
    }

    if (STATE === "loading") {
      if (statusText) { statusText.textContent = "Загрузка..."; statusText.className = "balance-value"; }
      if (statusSubtitle) statusSubtitle.textContent = "";
      if (statusPillText) statusPillText.textContent = "Загрузка...";
      if (statusPill) statusPill.className = "action-btn action-btn_status";
      if (keyInput) keyInput.value = "";
      return;
    }

    if (STATE === "error") {
      if (statusText) { statusText.textContent = "Ошибка загрузки"; statusText.className = "balance-value"; }
      if (statusSubtitle) statusSubtitle.textContent = "";
      if (statusPillText) statusPillText.textContent = "Ошибка";
      if (statusPill) statusPill.className = "action-btn action-btn_status";
      if (keyInput) keyInput.value = "";
      setBuyButtonLabel("Купить ключ");
      return;
    }

    if (STATE === "ACTIVE") {
      var sub = data.subscription;
      var left = daysLeft(sub.expires_at);
      if (statusText) { statusText.textContent = "Активен"; statusText.className = "balance-value active"; }
      if (statusSubtitle) statusSubtitle.textContent = "Осталось " + left + " " + pluralDays(left);
      if (statusPillText) statusPillText.textContent = "Активен";
      if (statusPill) statusPill.className = "action-btn action-btn_status status_active";
      if (keyInput) keyInput.value = sub.key || "";
      setBuyButtonLabel("Продлить ключ");
    } else if (STATE === "EXPIRED") {
      if (statusText) { statusText.textContent = "Просрочен"; statusText.className = "balance-value expired"; }
      if (statusSubtitle) statusSubtitle.textContent = "";
      if (statusPillText) statusPillText.textContent = "Просрочен";
      if (statusPill) statusPill.className = "action-btn action-btn_status status_expired";
      if (keyInput) keyInput.value = data.subscription && data.subscription.key ? data.subscription.key : "";
      setBuyButtonLabel("Продлить ключ");
    } else if (STATE === "PAYMENT_PENDING") {
      if (statusText) { statusText.textContent = "Оплата в процессе..."; statusText.className = "balance-value pending"; }
      if (statusSubtitle) statusSubtitle.textContent = "";
      if (statusPillText) statusPillText.textContent = "Оплата...";
      if (statusPill) statusPill.className = "action-btn action-btn_status status_pending";
      if (keyInput) keyInput.value = "";
      setBuyButtonLabel("Купить ключ");
    } else {
      if (statusText) { statusText.textContent = "Ключ не активен"; statusText.className = "balance-value"; }
      if (statusSubtitle) statusSubtitle.textContent = "";
      if (statusPillText) statusPillText.textContent = "Ключ не активен";
      if (statusPill) statusPill.className = "action-btn action-btn_status";
      if (keyInput) keyInput.value = "";
      setBuyButtonLabel("Купить ключ");
    }
  }

  function fetchProfile() {
    var initData = tg.initData || "";

    STATE = "loading";
    render();

    fetch(apiBase + "/api/me", {
      method: "GET",
      headers: {
        "X-Telegram-Init-Data": initData,
      },
    })
      .then(function (res) {
        if (res.status === 401) {
          STATE = "NO_SUBSCRIPTION";
          data = { subscription: null };
          render();
          bindEvents();
          return;
        }
        if (!res.ok) throw new Error("API error " + res.status);
        return res.json();
      })
      .then(function (json) {
        if (!json) return;
        data = json;
        STATE = json.state === "active" ? "ACTIVE" : json.state === "expired" ? "EXPIRED" : json.state === "payment_pending" ? "PAYMENT_PENDING" : "NO_SUBSCRIPTION";
        render();
        bindEvents();
      })
      .catch(function () {
        STATE = "error";
        render();
        bindEvents();
      });
  }

  function bindEvents() {
    var tariff1 = document.getElementById("tariff-1");
    var tariff3 = document.getElementById("tariff-3");
    var btnBuyKeyTop = document.getElementById("btn-buy-key-top");
    var btnTariffsBack = document.getElementById("btn-tariffs-back");
    var btnPay = document.getElementById("btn-pay");
    var btnCopy = document.getElementById("btn-copy");

    function setSelected(card) {
      document.querySelectorAll(".tariff-row").forEach(function (c) {
        c.classList.remove("tariff-row_selected");
      });
      card.classList.add("tariff-row_selected");
      selectedTariff.months = parseInt(card.dataset.months, 10);
      selectedTariff.price = parseInt(card.dataset.price, 10);
    }

    if (tariff1) {
      tariff1.onclick = function () {
        tg.HapticFeedback && tg.HapticFeedback.selectionChanged();
        setSelected(this);
      };
    }
    if (tariff3) {
      tariff3.onclick = function () {
        tg.HapticFeedback && tg.HapticFeedback.selectionChanged();
        setSelected(this);
      };
    }

    if (btnBuyKeyTop) {
      btnBuyKeyTop.onclick = function () {
        tg.HapticFeedback && tg.HapticFeedback.impactOccurred("medium");
        showScreen("tariffs");
      };
    }
    if (btnTariffsBack) {
      btnTariffsBack.onclick = function () {
        tg.HapticFeedback && tg.HapticFeedback.impactOccurred("light");
        showScreen("main");
      };
    }
    if (btnPay) {
      btnPay.onclick = function () {
        tg.HapticFeedback && tg.HapticFeedback.impactOccurred("medium");
        tg.showAlert &&
          tg.showAlert(
            "Тариф: " + selectedTariff.months + " мес, " + selectedTariff.price + " ₽. Оплата через ЮKassa будет подключена в Итерации 5."
          );
      };
    }

    if (btnCopy) {
      btnCopy.onclick = function () {
        var input = document.getElementById("key-input");
        if (!input || !input.value.trim()) {
          tg.showAlert && tg.showAlert("Сначала приобретите ключ");
          return;
        }
        tg.HapticFeedback && tg.HapticFeedback.notificationOccurred("success");
        input.select();
        input.setSelectionRange(0, 99999);
        try {
          navigator.clipboard.writeText(input.value);
          tg.showAlert && tg.showAlert("Ключ скопирован");
        } catch (e) {
          tg.showAlert && tg.showAlert("Скопируйте ключ вручную");
        }
      };
    }
  }

  fetchProfile();
})();
