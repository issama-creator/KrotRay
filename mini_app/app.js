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

  var REFER_LINK = "https://t.me/krotraybot";

  var STATE = "NO_SUBSCRIPTION";
  var data = { subscription: null };

  var selectedTariff = { tariffId: "1m", months: 1, price: 100 };
  var selectedPaymentMethod = "sbp"; // "sbp" | "card"

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
    var payment = document.getElementById("screen-payment");
    if (main) main.classList.toggle("screen_hidden", name !== "main");
    if (tariffs) tariffs.classList.toggle("screen_hidden", name !== "tariffs");
    if (payment) payment.classList.toggle("screen_hidden", name !== "payment");
    if (name === "payment") {
      var paymentAmountEl = document.getElementById("payment-amount");
      if (paymentAmountEl) paymentAmountEl.textContent = selectedTariff.price + " ₽";
    }
  }

  function render() {
    var statusPill = document.getElementById("status-pill");
    var statusPillText = document.getElementById("status-pill-text");
    var keyInput = document.getElementById("key-input");
    var btnBuyKeyTopText = document.getElementById("btn-buy-key-top-text");

    function setBuyButtonLabel(label) {
      if (btnBuyKeyTopText) btnBuyKeyTopText.textContent = label;
    }

    if (STATE === "loading") {
      if (statusPillText) statusPillText.textContent = "Загрузка…";
      if (statusPill) statusPill.className = "status-card status_card_loading";
      if (keyInput) keyInput.value = "";
      return;
    }

    if (STATE === "error") {
      if (statusPillText) statusPillText.textContent = "Ошибка загрузки";
      if (statusPill) statusPill.className = "status-card status_card_error";
      if (keyInput) keyInput.value = "";
      setBuyButtonLabel("Получить ключ");
      return;
    }

    if (STATE === "ACTIVE") {
      var sub = data.subscription;
      var left = daysLeft(sub.expires_at);
      if (statusPillText) statusPillText.textContent = "Активна · осталось " + left + " " + pluralDays(left);
      if (statusPill) statusPill.className = "status-card status_card_active";
      if (keyInput) keyInput.value = (sub.vless_url || sub.key) || "";
      setBuyButtonLabel("Продлить ключ");
    } else if (STATE === "EXPIRED") {
      if (statusPillText) statusPillText.textContent = "Просрочена";
      if (statusPill) statusPill.className = "status-card status_card_expired";
      if (keyInput) keyInput.value = (data.subscription && (data.subscription.vless_url || data.subscription.key)) || "";
      setBuyButtonLabel("Продлить ключ");
    } else if (STATE === "PAYMENT_PENDING") {
      if (statusPillText) statusPillText.textContent = "Ожидание оплаты";
      if (statusPill) statusPill.className = "status-card status_card_pending";
      if (keyInput) keyInput.value = "";
      setBuyButtonLabel("Получить ключ");
    } else {
      if (statusPillText) statusPillText.textContent = "Нет активной подписки";
      if (statusPill) statusPill.className = "status-card";
      if (keyInput) keyInput.value = "";
      setBuyButtonLabel("Получить ключ");
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
    var btnTariffsNext = document.getElementById("btn-tariffs-next");
    var btnPaymentBack = document.getElementById("btn-payment-back");
    var btnPay = document.getElementById("btn-pay");
    var btnCopy = document.getElementById("btn-copy");

    function setSelected(card) {
      document.querySelectorAll(".tariff-row").forEach(function (c) {
        c.classList.remove("tariff-row_selected");
      });
      card.classList.add("tariff-row_selected");
      selectedTariff.tariffId = card.dataset.tariffId || (parseInt(card.dataset.months, 10) === 1 ? "1m" : "3m");
      selectedTariff.months = parseInt(card.dataset.months, 10);
      selectedTariff.price = parseInt(card.dataset.price, 10);
      var payAmount = document.getElementById("pay-amount");
      if (payAmount) payAmount.textContent = selectedTariff.price + " ₽";
    }

    function setPaymentMethod(method) {
      selectedPaymentMethod = method;
      document.querySelectorAll(".payment-method__row").forEach(function (r) {
        r.classList.toggle("payment-method__row_selected", r.dataset.method === method);
      });
    }

    var tariffFamily5 = document.getElementById("tariff-family5");
    function bindTariffRow(el) {
      if (!el) return;
      el.onclick = function () {
        tg.HapticFeedback && tg.HapticFeedback.selectionChanged();
        setSelected(this);
      };
    }
    bindTariffRow(tariff1);
    bindTariffRow(tariff3);
    bindTariffRow(tariffFamily5);

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
    if (btnTariffsNext) {
      btnTariffsNext.onclick = function () {
        tg.HapticFeedback && tg.HapticFeedback.impactOccurred("medium");
        showScreen("payment");
      };
    }
    if (btnPaymentBack) {
      btnPaymentBack.onclick = function () {
        tg.HapticFeedback && tg.HapticFeedback.impactOccurred("light");
        showScreen("tariffs");
      };
    }
    var methodSbp = document.getElementById("method-sbp");
    var methodCard = document.getElementById("method-card");
    var paymentMethodSbp = document.getElementById("payment-method-sbp");
    var paymentMethodCard = document.getElementById("payment-method-card");
    function bindPaymentMethodRow(el, method) {
      if (!el) return;
      el.onclick = function () {
        tg.HapticFeedback && tg.HapticFeedback.selectionChanged();
        setPaymentMethod(method);
      };
    }
    if (methodSbp) bindPaymentMethodRow(methodSbp, "sbp");
    if (methodCard) bindPaymentMethodRow(methodCard, "card");
    if (paymentMethodSbp) bindPaymentMethodRow(paymentMethodSbp, "sbp");
    if (paymentMethodCard) bindPaymentMethodRow(paymentMethodCard, "card");

    if (btnPay) {
      btnPay.onclick = function () {
        tg.HapticFeedback && tg.HapticFeedback.impactOccurred("medium");
        var tariffId = selectedTariff.tariffId || (selectedTariff.months === 1 ? "1m" : "3m");
        var initData = tg.initData || "";
        btnPay.disabled = true;
        fetch(apiBase + "/api/payments/create", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Telegram-Init-Data": initData,
          },
          body: JSON.stringify({ tariff: tariffId, method: selectedPaymentMethod }),
        })
          .then(function (res) {
            return res.json().then(function (json) {
              if (!res.ok) {
                var detail = json.detail;
                var msg = "Ошибка создания платежа";
                if (detail != null) {
                  msg = Array.isArray(detail) ? (detail[0] && detail[0].msg ? detail[0].msg : detail.join(" ")) : String(detail);
                }
                throw new Error(msg);
              }
              return json;
            });
          })
          .then(function (json) {
            var url = json.confirmation_url;
            if (url && tg.openLink) {
              tg.openLink(url);
            } else if (url) {
              window.open(url, "_blank");
            } else {
              tg.showAlert && tg.showAlert("Не получена ссылка на оплату");
            }
          })
          .catch(function (err) {
            tg.showAlert && tg.showAlert(err.message || "Ошибка. Попробуйте позже.");
          })
          .finally(function () {
            btnPay.disabled = false;
          });
      };
    }

    function showToast(message) {
      var el = document.getElementById("toast");
      if (!el) return;
      el.textContent = message;
      el.classList.add("toast_visible");
      clearTimeout(el._toastTimer);
      el._toastTimer = setTimeout(function () {
        el.classList.remove("toast_visible");
      }, 2500);
    }

    if (btnCopy) {
      btnCopy.onclick = function () {
        var input = document.getElementById("key-input");
        if (!input || !input.value.trim()) {
          tg.showAlert && tg.showAlert("Сначала получите ключ");
          return;
        }
        tg.HapticFeedback && tg.HapticFeedback.notificationOccurred("success");
        try {
          navigator.clipboard.writeText(input.value);
          showToast("Ключ скопирован");
        } catch (e) {
          tg.showAlert && tg.showAlert("Скопируйте вручную");
        }
      };
    }

    var btnReferShare = document.getElementById("btn-refer-share");
    var btnReferCopy = document.getElementById("btn-refer-copy");
    if (btnReferShare) {
      btnReferShare.onclick = function () {
        tg.HapticFeedback && tg.HapticFeedback.impactOccurred("light");
        var shareUrl = "https://t.me/share/url?url=" + encodeURIComponent(REFER_LINK) + "&text=" + encodeURIComponent("Присоединяйся к KrotRay VPN");
        if (tg.openTelegramLink) {
          tg.openTelegramLink(shareUrl);
        } else if (tg.openLink) {
          tg.openLink(shareUrl);
        } else {
          window.open(shareUrl, "_blank");
        }
      };
    }
    if (btnReferCopy) {
      btnReferCopy.onclick = function () {
        tg.HapticFeedback && tg.HapticFeedback.notificationOccurred("success");
        try {
          navigator.clipboard.writeText(REFER_LINK);
          showToast("Ссылка скопирована");
        } catch (e) {
          tg.showAlert && tg.showAlert("Скопируйте ссылку вручную");
        }
      };
    }
  }

  fetchProfile();
})();
