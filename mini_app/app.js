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
    var hasKeyBlock = document.getElementById("has-key-block");
    var buySection = document.getElementById("buy-section");
    var btnBuyKey = document.getElementById("btn-buy-key");

    if (STATE === "loading") {
      statusText.textContent = "Загрузка...";
      statusText.className = "status-text";
      hasKeyBlock.classList.add("hidden");
      buySection.classList.add("hidden");
      return;
    }

    if (STATE === "error") {
      statusText.textContent = "Ошибка загрузки";
      statusText.className = "status-text";
      hasKeyBlock.classList.add("hidden");
      buySection.classList.remove("hidden");
      btnBuyKey.textContent = "Купить ключ";
      return;
    }

    if (STATE === "ACTIVE") {
      var sub = data.subscription;
      statusText.textContent = "Активен до " + formatDate(sub.expires_at);
      statusText.className = "status-text active";
      hasKeyBlock.classList.remove("hidden");
      buySection.classList.add("hidden");
      var key = sub.key || "";
      document.getElementById("key-input").value = key || "Ключ будет доступен после настройки сервера";
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
    var btnCopy = document.getElementById("btn-copy");

    if (!tariff1 || !tariff3) return;

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

    if (btnBuyKey) {
      btnBuyKey.onclick = function () {
        tg.HapticFeedback && tg.HapticFeedback.impactOccurred("medium");
        tg.showAlert &&
          tg.showAlert(
            "Тариф: " +
              selectedTariff.months +
              " мес, " +
              selectedTariff.price +
              " ₽. Оплата через ЮKassa будет подключена в Итерации 5."
          );
      };
    }

    if (btnCopy) {
      btnCopy.onclick = function () {
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
      };
    }
  }

  fetchProfile();
})();
