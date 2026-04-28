(function () {
    "use strict";

    var usernameInput = document.querySelector('input[name="username"]');
    var alertStack = document.querySelector('.login-alert-stack-v5');
    if (!usernameInput || !alertStack) {
        return;
    }

    var initialUsername = (usernameInput.value || "").trim();

    function syncAlertVisibility() {
        var current = (usernameInput.value || "").trim();
        var shouldHide = !current || (initialUsername && current !== initialUsername);
        alertStack.style.display = shouldHide ? "none" : "";
    }

    usernameInput.addEventListener("input", syncAlertVisibility);
    syncAlertVisibility();
})();
