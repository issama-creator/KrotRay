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

  function render() {
    var statusText = document.getElementById("status-text");
    var statusSubtitle = document.getElementById("status-subtitle");
    var statusPill = document.getElementById("status-pill");
    var statusPillText = document.getElementById("status-pill-text");
    var keyInput = document.getElementById("key-input");
    var buySection = document.getElementById("buy-section");
    var btnBuyKey = document.getElementById("btn-buy-key");
    var btnBuyKeyTopText = document.getElementById("btn-buy-key-top-text");

    function setBuyButtonLabel(label) {
      if (btnBuyKey) btnBuyKey.textContent = label;
      if (btnBuyKeyTopText) btnBuyKeyTopText.textContent = label;
    }

    if (STATE === "loading") {
      if (statusText) { statusText.textContent = "Загрузка..."; statusText.className = "balance-value"; }
      if (statusSubtitle) statusSubtitle.textContent = "";
      if (statusPillText) statusPillText.textContent = "Загрузка...";
      if (statusPill) statusPill.className = "action-btn action-btn_status";
      if (keyInput) keyInput.value = "";
      buySection.classList.add("hidden");
      return;
    }

    if (STATE === "error") {
      if (statusText) { statusText.textContent = "Ошибка загрузки"; statusText.className = "balance-value"; }
      if (statusSubtitle) statusSubtitle.textContent = "";
      if (statusPillText) statusPillText.textContent = "Ошибка";
      if (statusPill) statusPill.className = "action-btn action-btn_status";
      if (keyInput) keyInput.value = "";
      buySection.classList.remove("hidden");
      setBuyButtonLabel("Купить ключ");
      return;
    }

    if (STATE === "ACTIVE") {
      var sub = data.subscription;
      if (statusText) { statusText.textContent = "Активен"; statusText.className = "balance-value active"; }
      if (statusSubtitle) statusSubtitle.textContent = "до " + formatDate(sub.expires_at);
      if (statusPillText) statusPillText.textContent = "Активен";
      if (statusPill) statusPill.className = "action-btn action-btn_status status_active";
      if (keyInput) keyInput.value = sub.key || "";
      buySection.classList.add("hidden");
      setBuyButtonLabel("Продлить ключ");
    } else if (STATE === "EXPIRED") {
      if (statusText) { statusText.textContent = "Просрочен"; statusText.className = "balance-value expired"; }
      if (statusSubtitle) statusSubtitle.textContent = "";
      if (statusPillText) statusPillText.textContent = "Просрочен";
      if (statusPill) statusPill.className = "action-btn action-btn_status status_expired";
      if (keyInput) keyInput.value = data.subscription && data.subscription.key ? data.subscription.key : "";
      buySection.classList.remove("hidden");
      setBuyButtonLabel("Продлить ключ");
    } else if (STATE === "PAYMENT_PENDING") {
      if (statusText) { statusText.textContent = "Оплата в процессе..."; statusText.className = "balance-value pending"; }
      if (statusSubtitle) statusSubtitle.textContent = "";
      if (statusPillText) statusPillText.textContent = "Оплата...";
      if (statusPill) statusPill.className = "action-btn action-btn_status status_pending";
      if (keyInput) keyInput.value = "";
      buySection.classList.add("hidden");
      setBuyButtonLabel("Купить ключ");
    } else {
      if (statusText) { statusText.textContent = "Ключ не активен"; statusText.className = "balance-value"; }
      if (statusSubtitle) statusSubtitle.textContent = "";
      if (statusPillText) statusPillText.textContent = "Ключ не активен";
      if (statusPill) statusPill.className = "action-btn action-btn_status";
      if (keyInput) keyInput.value = "";
      buySection.classList.remove("hidden");
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
    var btnBuyKey = document.getElementById("btn-buy-key");
    var btnBuyKeyTop = document.getElementById("btn-buy-key-top");
    var btnCopy = document.getElementById("btn-copy");

    if (!tariff1 || !tariff3) return;

    function onBuyKey() {
      tg.HapticFeedback && tg.HapticFeedback.impactOccurred("medium");
      tg.showAlert &&
        tg.showAlert(
          "Тариф: " +
            selectedTariff.months +
            " мес, " +
            selectedTariff.price +
            " ₽. Оплата через ЮKassa будет подключена в Итерации 5."
        );
    }

    function setSelected(card) {
      document.querySelectorAll(".tariff-row").forEach(function (c) {
        c.classList.remove("tariff-row_selected");
      });
      card.classList.add("tariff-row_selected");
      selectedTariff.months = parseInt(card.dataset.months, 10);
      selectedTariff.price = parseInt(card.dataset.price, 10);
    }

    tariff1.onclick = function () {
      tg.HapticFeedback && tg.HapticFeedback.selectionChanged();
      setSelected(this);
    };
    tariff3.onclick = function () {
      tg.HapticFeedback && tg.HapticFeedback.selectionChanged();
      setSelected(this);
    };

    if (btnBuyKey) btnBuyKey.onclick = onBuyKey;
    if (btnBuyKeyTop) btnBuyKeyTop.onclick = onBuyKey;

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
