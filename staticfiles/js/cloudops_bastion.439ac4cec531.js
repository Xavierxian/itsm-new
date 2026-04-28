(function () {
    var page = document.querySelector("[data-bastion-page]");
    if (!page) {
        return;
    }

    var configReady = page.getAttribute("data-config-ready") === "1";
    var defaultCloudId = page.getAttribute("data-default-cloud-id") || "";
    var summaryUrl = page.getAttribute("data-summary-url") || "";
    var hostsUrl = page.getAttribute("data-hosts-url") || "";
    var onlineCountUrl = page.getAttribute("data-online-count-url") || "";
    var exportUrl = page.getAttribute("data-export-url") || "";
    var pingUrl = page.getAttribute("data-ping-url") || "";
    var credentialsUrlTemplate = page.getAttribute("data-credentials-url-template") || "";
    var restartUrlTemplate = page.getAttribute("data-restart-url-template") || "";
    var deleteUrlTemplate = page.getAttribute("data-delete-url-template") || "";
    var userInfoUrlTemplate = page.getAttribute("data-user-info-url-template") || "";
    var hostUserAuthUrl = page.getAttribute("data-host-user-auth-url") || "";
    var credentialPasswordUrl = page.getAttribute("data-credential-password-url") || "";

    var refreshBtn = document.getElementById("bastion-refresh-btn");
    var refreshTableBtn = document.getElementById("bastion-refresh-table-btn");
    var loadHostsBtn = document.getElementById("bastion-load-hosts-btn");
    var pingBtn = document.getElementById("bastion-ping-btn");
    var searchInput = document.getElementById("bastion-search");
    var cloudIdInput = document.getElementById("bastion-cloud-id");
    var exportLink = document.getElementById("bastion-export-link");
    var tableBody = document.getElementById("bastion-table-body");
    var hostsListSection = document.getElementById("bastion-hosts-list-section");
    var noticeNode = document.getElementById("bastion-notice");

    var totalHostsNode = document.getElementById("bastion-total-hosts");
    var onlineHostsNode = document.getElementById("bastion-online-hosts");
    var totalUsersNode = document.getElementById("bastion-total-users");
    var totalCredentialsNode = document.getElementById("bastion-total-credentials");
    var onlineUsersNode = document.getElementById("bastion-online-users");
    var onlineUsersChipNode = document.getElementById("bastion-online-users-chip");

    var hostActionInput = document.getElementById("bastion-host-action-input");
    var restartByInputBtn = document.getElementById("bastion-restart-by-input-btn");
    var deleteByInputBtn = document.getElementById("bastion-delete-by-input-btn");

    var userAccountInput = document.getElementById("bastion-user-account-input");
    var queryUserBtn = document.getElementById("bastion-query-user-btn");
    var userQueryResult = document.getElementById("bastion-user-query-result");
    var addAuthBtn = document.getElementById("bastion-add-auth-btn");

    var passwordHostInput = document.getElementById("bastion-password-host-input");
    var passwordInput = document.getElementById("bastion-password-input");
    var changePasswordBtn = document.getElementById("bastion-change-password-btn");

    var credentialModal = document.getElementById("bastion-credential-modal");
    var credentialModalContent = document.getElementById("bastion-credential-content");
    var credentialModalCloseBtn = document.getElementById("bastion-credential-close-btn");
    var credentialModalBackdrop = credentialModal ? credentialModal.querySelector("[data-credential-close]") : null;

    var authModal = document.getElementById("bastion-auth-modal");
    var authModalCloseBtn = document.getElementById("bastion-auth-close-btn");
    var authModalBackdrop = authModal ? authModal.querySelector("[data-auth-close]") : null;
    var authHostInput = document.getElementById("bastion-auth-host-input");
    var authAccountInput = document.getElementById("bastion-auth-account-input");
    var authSubmitBtn = document.getElementById("bastion-auth-submit-btn");
    var authHostIdTip = document.getElementById("bastion-auth-host-id-tip");
    var authUserIdTip = document.getElementById("bastion-auth-user-id-tip");

    var state = {
        hosts: [],
        currentUserInfo: null,
        currentUserId: "",
        authResolvedHostId: "",
        authResolvedUserId: "",
        authResolvedUserInfo: null,
    };
    var noticeTimer = null;
    var authHostResolveTimer = null;
    var authUserResolveTimer = null;
    var authHostResolveToken = 0;
    var authUserResolveToken = 0;

    function normalizeText(value) {
        return String(value || "").trim().toLowerCase();
    }

    function isLikelyIpv4(value) {
        var text = String(value || "").trim();
        if (!text) {
            return false;
        }
        if (!/^(?:\d{1,3}\.){3}\d{1,3}$/.test(text)) {
            return false;
        }
        var parts = text.split(".");
        for (var i = 0; i < parts.length; i += 1) {
            var num = Number(parts[i]);
            if (!Number.isInteger(num) || num < 0 || num > 255) {
                return false;
            }
        }
        return true;
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function getCloudId() {
        var value = cloudIdInput && cloudIdInput.value ? cloudIdInput.value.trim() : "";
        return value || defaultCloudId;
    }

    function showDashIfEmpty(value) {
        return value === null || value === undefined || value === "" ? "--" : String(value);
    }

    function syncModalBodyClass() {
        var hasOpenModal =
            (credentialModal && !credentialModal.hidden) ||
            (authModal && !authModal.hidden);
        if (hasOpenModal) {
            document.body.classList.add("modal-open");
        } else {
            document.body.classList.remove("modal-open");
        }
    }

    function focusHostsList() {
        if (hostsListSection && typeof hostsListSection.scrollIntoView === "function") {
            hostsListSection.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    function setNotice(type, text, autoHideMs) {
        if (!noticeNode) {
            return;
        }
        if (noticeTimer) {
            window.clearTimeout(noticeTimer);
            noticeTimer = null;
        }
        if (!text) {
            noticeNode.hidden = true;
            noticeNode.className = "bastion-alert-v2";
            noticeNode.textContent = "";
            return;
        }

        noticeNode.hidden = false;
        noticeNode.textContent = text;
        if (type === "error") {
            noticeNode.className = "bastion-alert-v2 bastion-alert-danger-v2";
        } else if (type === "warning") {
            noticeNode.className = "bastion-alert-v2 bastion-alert-warning-v2";
        } else {
            noticeNode.className = "bastion-alert-v2 bastion-alert-success-v2";
        }

        var hideDelay = typeof autoHideMs === "number" ? autoHideMs : 3000;
        if (hideDelay > 0) {
            noticeTimer = window.setTimeout(function () {
                setNotice("", "");
            }, hideDelay);
        }
    }

    function getCsrfToken() {
        var name = "csrftoken=";
        var cookies = document.cookie ? document.cookie.split(";") : [];
        for (var i = 0; i < cookies.length; i += 1) {
            var cookie = cookies[i].trim();
            if (cookie.indexOf(name) === 0) {
                return decodeURIComponent(cookie.substring(name.length));
            }
        }
        return "";
    }

    function buildUrl(baseUrl, params) {
        var url = new URL(baseUrl, window.location.origin);
        Object.keys(params || {}).forEach(function (key) {
            var value = params[key];
            if (value === null || value === undefined || value === "") {
                return;
            }
            url.searchParams.set(key, value);
        });
        return url.pathname + url.search;
    }

    function requestJson(url, options) {
        return fetch(url, Object.assign({ credentials: "same-origin" }, options || {})).then(function (response) {
            return response
                .json()
                .catch(function () {
                    if (response.status === 403) {
                        return { success: false, error: "请求被拒绝（CSRF/Origin 校验失败），请刷新页面后重试。" };
                    }
                    return { success: false, error: "响应格式错误" };
                })
                .then(function (data) {
                    if (!response.ok || !data.success) {
                        var errorText = (data && (data.error || data.details)) || ("请求失败（HTTP " + response.status + "）");
                        throw new Error(errorText);
                    }
                    return data;
                });
        });
    }

    function updateExportLink() {
        if (!exportLink || !exportUrl) {
            return;
        }
        var url = new URL(exportUrl, window.location.origin);
        var cloudId = getCloudId();
        if (cloudId) {
            url.searchParams.set("cloud_id", cloudId);
        }
        exportLink.href = url.pathname + url.search;
    }

    function renderSummary(summary) {
        summary = summary || {};
        if (totalHostsNode) {
            totalHostsNode.textContent = showDashIfEmpty(summary.total_hosts);
        }
        if (onlineHostsNode) {
            onlineHostsNode.textContent = showDashIfEmpty(summary.online_hosts);
        }
        if (totalUsersNode) {
            totalUsersNode.textContent = showDashIfEmpty(summary.total_users);
        }
        if (totalCredentialsNode) {
            totalCredentialsNode.textContent = showDashIfEmpty(summary.total_credentials);
        }
        if (onlineUsersNode) {
            onlineUsersNode.textContent = showDashIfEmpty(summary.online_users);
        }
        if (onlineUsersChipNode) {
            onlineUsersChipNode.textContent = showDashIfEmpty(summary.online_users);
        }
    }

    function setLoadingState(text) {
        if (!tableBody) {
            return;
        }
        tableBody.innerHTML = '<tr><td colspan="6"><div class="empty-inline empty-inline-v4">' + escapeHtml(text || "正在加载...") + "</div></td></tr>";
    }

    function hostStatusLabel(host) {
        if (typeof host.online === "boolean") {
            return host.online ? "在线" : "离线";
        }
        return host.status || "--";
    }

    function hostStatusTone(host) {
        if (typeof host.online === "boolean") {
            return host.online ? "success" : "danger";
        }
        return "";
    }

    function renderRows() {
        if (!tableBody) {
            return;
        }
        var keyword = normalizeText(searchInput && searchInput.value);
        var rows = state.hosts.filter(function (host) {
            if (!keyword) {
                return true;
            }
            var aggregate = [
                host.hostId,
                host.hostName,
                host.hostIp,
                host.operatingSystem,
                host.description,
                host.status,
            ]
                .join(" ")
                .toLowerCase();
            return aggregate.indexOf(keyword) >= 0;
        });

        if (!rows.length) {
            tableBody.innerHTML = '<tr><td colspan="6"><div class="empty-inline empty-inline-v4">没有匹配数据</div></td></tr>';
            return;
        }

        tableBody.innerHTML = rows
            .map(function (host) {
                var hostId = host.hostId || "";
                var hostName = host.hostName || "";
                var hostIp = host.hostIp || "";
                if (!hostIp && isLikelyIpv4(hostName)) {
                    hostIp = hostName;
                    hostName = "";
                }
                if (normalizeText(hostName) && normalizeText(hostName) === normalizeText(hostIp || "")) {
                    hostName = "";
                }
                var status = hostStatusLabel(host);
                var tone = hostStatusTone(host);
                var statusHtml = tone
                    ? '<span class="result-badge-v4 result-badge-v4-' + tone + '">' + escapeHtml(status) + "</span>"
                    : escapeHtml(status);
                return (
                    "<tr>" +
                    "<td>" + escapeHtml(hostIp || "-") + "</td>" +
                    "<td>" + escapeHtml(host.operatingSystem || "-") + "</td>" +
                    "<td>" + escapeHtml(host.description || "-") + "</td>" +
                    "<td>" + statusHtml + "</td>" +
                    "<td><code>" + escapeHtml(hostId || "-") + "</code></td>" +
                    '<td class="bastion-row-actions-v2">' +
                    '<button class="secondary-button bastion-mini-btn-v2" type="button" data-action="credentials" data-host-id="' + escapeHtml(hostId) + '">凭据</button>' +
                    "</td>" +
                    "</tr>"
                );
            })
            .join("");
    }

    function loadSummary(forceRefresh) {
        if (!configReady || !summaryUrl) {
            return Promise.resolve();
        }
        var url = buildUrl(summaryUrl, {
            cloud_id: getCloudId(),
            refresh: forceRefresh ? "1" : "",
        });
        return requestJson(url)
            .then(function (data) {
                renderSummary(data.summary || {});
            })
            .catch(function () {
                renderSummary({});
            });
    }

    function loadOnlineCount() {
        if (!configReady || !onlineCountUrl || (!onlineUsersChipNode && !onlineUsersNode)) {
            return Promise.resolve();
        }
        return requestJson(onlineCountUrl)
            .then(function (data) {
                var display = showDashIfEmpty(data.count);
                if (onlineUsersChipNode) {
                    onlineUsersChipNode.textContent = display;
                }
                if (onlineUsersNode) {
                    onlineUsersNode.textContent = display;
                }
            })
            .catch(function () {
                if (onlineUsersChipNode) {
                    onlineUsersChipNode.textContent = "--";
                }
                if (onlineUsersNode) {
                    onlineUsersNode.textContent = "--";
                }
            });
    }

    function loadHosts(forceRefresh) {
        if (!configReady) {
            setNotice("warning", "JumpServer 凭据未配置，无法加载主机清单。");
            setLoadingState("无法加载：未配置 JumpServer 凭据。");
            return Promise.resolve([]);
        }
        setLoadingState("正在拉取堡垒机清单...");
        var url = buildUrl(hostsUrl, {
            cloud_id: getCloudId(),
            refresh: forceRefresh ? "1" : "",
        });
        return requestJson(url)
            .then(function (data) {
                state.hosts = Array.isArray(data.hosts) ? data.hosts : [];
                renderRows();
                if (forceRefresh) {
                    setNotice("success", "主机清单已刷新");
                }
                return state.hosts;
            })
            .catch(function (error) {
                setNotice("error", error.message || "主机清单加载失败");
                setLoadingState("加载失败，请稍后重试。");
                return [];
            });
    }

    function ensureHostsLoaded() {
        return state.hosts.length ? Promise.resolve(state.hosts) : loadHosts(false);
    }

    function resolveHostId(identifier) {
        var keyword = normalizeText(identifier);
        if (!keyword) {
            throw new Error("请输入主机IP或主机标识");
        }
        var exactId = state.hosts.find(function (host) {
            return normalizeText(host.hostId) === keyword;
        });
        if (exactId) {
            return exactId.hostId;
        }
        var exactHost = state.hosts.find(function (host) {
            return normalizeText(host.hostName) === keyword || normalizeText(host.hostIp) === keyword;
        });
        if (exactHost) {
            return exactHost.hostId;
        }
        var partial = state.hosts.filter(function (host) {
            var aggregate = [host.hostId, host.hostName, host.hostIp, host.description].join(" ").toLowerCase();
            return aggregate.indexOf(keyword) >= 0;
        });
        if (partial.length === 1) {
            return partial[0].hostId;
        }
        if (partial.length > 1) {
            throw new Error("匹配到多个主机，请输入更精确的主机标识");
        }
        throw new Error("未匹配到目标主机，请检查输入");
    }

    function withHostUrl(template, hostId) {
        return String(template || "").replace("__HOST_ID__", encodeURIComponent(hostId));
    }

    function openCredentialModal(content) {
        if (!credentialModal || !credentialModalContent) {
            return;
        }
        credentialModalContent.textContent = JSON.stringify(content || {}, null, 2);
        credentialModal.hidden = false;
        syncModalBodyClass();
    }

    function closeCredentialModal() {
        if (!credentialModal) {
            return;
        }
        credentialModal.hidden = true;
        syncModalBodyClass();
    }

    function openAuthModal() {
        if (!authModal) {
            return;
        }
        clearAuthResolveTimers();
        authHostResolveToken += 1;
        authUserResolveToken += 1;
        state.authResolvedHostId = "";
        state.authResolvedUserId = "";
        state.authResolvedUserInfo = null;
        setAuthHostTip("", "", "");
        setAuthUserTip("", "", "");
        if (authHostInput) {
            authHostInput.value = (hostActionInput && hostActionInput.value ? hostActionInput.value : "").trim();
        }
        if (authAccountInput) {
            authAccountInput.value = (userAccountInput && userAccountInput.value ? userAccountInput.value : "").trim();
        }
        authModal.hidden = false;
        syncModalBodyClass();
        if (authHostInput) {
            authHostInput.focus();
        }
        if (authHostInput && authHostInput.value.trim()) {
            scheduleAuthHostResolve();
        }
        if (authAccountInput && authAccountInput.value.trim()) {
            scheduleAuthUserResolve();
        }
    }

    function closeAuthModal() {
        if (!authModal) {
            return;
        }
        clearAuthResolveTimers();
        authHostResolveToken += 1;
        authUserResolveToken += 1;
        authModal.hidden = true;
        syncModalBodyClass();
    }

    function clearAuthResolveTimers() {
        if (authHostResolveTimer) {
            window.clearTimeout(authHostResolveTimer);
            authHostResolveTimer = null;
        }
        if (authUserResolveTimer) {
            window.clearTimeout(authUserResolveTimer);
            authUserResolveTimer = null;
        }
    }

    function setAuthIdTip(node, label, idValue, message, tone) {
        if (!node) {
            return;
        }
        node.classList.remove("is-loading", "is-success", "is-error");
        if (tone === "loading") {
            node.classList.add("is-loading");
        } else if (tone === "success") {
            node.classList.add("is-success");
        } else if (tone === "error") {
            node.classList.add("is-error");
        }

        if (idValue) {
            node.textContent = label + "ID：" + idValue;
            return;
        }
        if (message) {
            node.textContent = message;
            return;
        }
        node.textContent = label + "ID：--";
    }

    function setAuthHostTip(hostId, message, tone) {
        setAuthIdTip(authHostIdTip, "主机", hostId, message, tone);
    }

    function setAuthUserTip(userId, message, tone) {
        setAuthIdTip(authUserIdTip, "用户", userId, message, tone);
    }

    function resolveAuthHostNow(silent) {
        var hostKeyword = authHostInput && authHostInput.value ? authHostInput.value.trim() : "";
        var token = ++authHostResolveToken;
        if (!hostKeyword) {
            state.authResolvedHostId = "";
            setAuthHostTip("", "", "");
            return Promise.resolve("");
        }

        setAuthHostTip("", "正在识别主机ID...", "loading");
        return ensureHostsLoaded().then(function () {
            if (token !== authHostResolveToken) {
                return state.authResolvedHostId || "";
            }
            try {
                var hostId = resolveHostId(hostKeyword);
                state.authResolvedHostId = hostId;
                setAuthHostTip(hostId, "", "success");
                return hostId;
            } catch (error) {
                state.authResolvedHostId = "";
                setAuthHostTip("", error.message || "未识别到主机ID", "error");
                if (silent) {
                    return "";
                }
                throw error;
            }
        });
    }

    function resolveAuthUserNow(silent) {
        var account = authAccountInput && authAccountInput.value ? authAccountInput.value.trim() : "";
        var token = ++authUserResolveToken;
        if (!account) {
            state.authResolvedUserId = "";
            state.authResolvedUserInfo = null;
            setAuthUserTip("", "", "");
            return Promise.resolve({ userInfo: null, userId: "" });
        }

        setAuthUserTip("", "正在识别用户ID...", "loading");
        return queryUserByAccount(account)
            .then(function (payload) {
                if (token !== authUserResolveToken) {
                    return { userInfo: state.authResolvedUserInfo, userId: state.authResolvedUserId };
                }
                state.authResolvedUserInfo = payload.userInfo;
                state.authResolvedUserId = payload.userId;
                setAuthUserTip(payload.userId, "", "success");
                return payload;
            })
            .catch(function (error) {
                if (token !== authUserResolveToken) {
                    return { userInfo: state.authResolvedUserInfo, userId: state.authResolvedUserId };
                }
                state.authResolvedUserId = "";
                state.authResolvedUserInfo = null;
                setAuthUserTip("", error.message || "未识别到用户ID", "error");
                if (silent) {
                    return { userInfo: null, userId: "" };
                }
                throw error;
            });
    }

    function scheduleAuthHostResolve() {
        if (!authModal || authModal.hidden) {
            return;
        }
        if (authHostResolveTimer) {
            window.clearTimeout(authHostResolveTimer);
        }
        authHostResolveTimer = window.setTimeout(function () {
            authHostResolveTimer = null;
            resolveAuthHostNow(true);
        }, 280);
    }

    function scheduleAuthUserResolve() {
        if (!authModal || authModal.hidden) {
            return;
        }
        if (authUserResolveTimer) {
            window.clearTimeout(authUserResolveTimer);
        }
        authUserResolveTimer = window.setTimeout(function () {
            authUserResolveTimer = null;
            resolveAuthUserNow(true);
        }, 320);
    }

    function extractUserId(payload) {
        if (payload && typeof payload === "object") {
            if (payload.userId || payload.user_id || payload.id) {
                return String(payload.userId || payload.user_id || payload.id);
            }
            var keys = Object.keys(payload);
            for (var i = 0; i < keys.length; i += 1) {
                var candidate = extractUserId(payload[keys[i]]);
                if (candidate) {
                    return candidate;
                }
            }
        }
        if (Array.isArray(payload)) {
            for (var j = 0; j < payload.length; j += 1) {
                var candidate2 = extractUserId(payload[j]);
                if (candidate2) {
                    return candidate2;
                }
            }
        }
        return "";
    }

    function queryUserByAccount(account) {
        var url = userInfoUrlTemplate.replace("__ACCOUNT__", encodeURIComponent(account));
        return requestJson(url).then(function (data) {
            var userInfo = data.user || {};
            var userId = data.user_id || extractUserId(userInfo);
            if (!userId) {
                throw new Error("查询到用户但缺少 User ID");
            }
            return { userInfo: userInfo, userId: userId };
        });
    }

    function renderUserQueryResult(userInfo, userId) {
        if (!userQueryResult) {
            return;
        }
        if (!userInfo) {
            userQueryResult.textContent = "未查询用户";
            return;
        }
        var account = userInfo.account || userInfo.userAccount || userInfo.username || userInfo.name || "--";
        var name = userInfo.userName || userInfo.name || userInfo.realName || "--";
        var safeUserId = userId || "--";
        userQueryResult.innerHTML =
            "<span>账号：" + escapeHtml(account) + "</span>" +
            "<span>姓名：" + escapeHtml(name) + "</span>" +
            "<span>User ID：" + escapeHtml(safeUserId) + "</span>";
    }

    function queryUser() {
        var account = userAccountInput && userAccountInput.value ? userAccountInput.value.trim() : "";
        if (!account) {
            setNotice("warning", "请输入用户账户");
            return;
        }
        queryUserByAccount(account)
            .then(function (payload) {
                state.currentUserInfo = payload.userInfo;
                state.currentUserId = payload.userId;
                renderUserQueryResult(payload.userInfo, payload.userId);
                setNotice("success", "用户查询成功");
            })
            .catch(function (error) {
                state.currentUserInfo = null;
                state.currentUserId = "";
                renderUserQueryResult(null, "");
                setNotice("error", error.message || "查询用户失败");
            });
    }

    function addUserAuth() {
        var hostKeyword = authHostInput && authHostInput.value ? authHostInput.value.trim() : "";
        var account = authAccountInput && authAccountInput.value ? authAccountInput.value.trim() : "";
        if (!hostKeyword) {
            setNotice("warning", "请输入主机IP");
            return;
        }
        if (!account) {
            setNotice("warning", "请输入用户账户");
            return;
        }

        if (authSubmitBtn) {
            authSubmitBtn.disabled = true;
            authSubmitBtn.textContent = "授权中...";
        }

        Promise.all([resolveAuthHostNow(false), resolveAuthUserNow(false)])
            .then(function (results) {
                var hostId = results[0] || "";
                var payload = results[1] || { userInfo: null, userId: "" };
                var userId = payload.userId || state.authResolvedUserId || "";
                if (!hostId) {
                    throw new Error("未识别到主机ID，请检查输入");
                }
                if (!userId) {
                    throw new Error("未识别到用户ID，请检查输入");
                }
                return requestJson(hostUserAuthUrl, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": getCsrfToken(),
                    },
                    body: JSON.stringify({
                        hostId: hostId,
                        userId: userId,
                        cloud_id: getCloudId(),
                    }),
                }).then(function () {
                    state.currentUserInfo = payload.userInfo || state.currentUserInfo;
                    state.currentUserId = userId;
                    renderUserQueryResult(payload.userInfo, userId);
                    if (hostActionInput) {
                        hostActionInput.value = hostId;
                    }
                    if (userAccountInput) {
                        userAccountInput.value = account;
                    }
                    if (authHostInput) {
                        authHostInput.value = hostKeyword;
                    }
                    if (authAccountInput) {
                        authAccountInput.value = account;
                    }
                    setAuthHostTip(hostId, "", "success");
                    setAuthUserTip(userId, "", "success");
                    closeAuthModal();
                    setNotice("success", "用户授权成功（Host ID: " + hostId + ", User ID: " + userId + "）");
                });
            })
            .catch(function (error) {
                setNotice("error", error.message || "添加授权失败");
            })
            .finally(function () {
                if (authSubmitBtn) {
                    authSubmitBtn.disabled = false;
                    authSubmitBtn.textContent = "确认授权";
                }
            });
    }

    function viewCredentials(hostId) {
        if (!hostId) {
            setNotice("warning", "缺少 host_id");
            return;
        }
        requestJson(withHostUrl(credentialsUrlTemplate, hostId))
            .then(function (data) {
                openCredentialModal(data.credentials || {});
            })
            .catch(function (error) {
                setNotice("error", error.message || "获取凭据失败");
            });
    }

    function runHostAction(action, hostId, confirmText) {
        if (!hostId) {
            setNotice("warning", "缺少 host_id");
            return;
        }
        if (confirmText && !window.confirm(confirmText)) {
            return;
        }
        var template = action === "restart" ? restartUrlTemplate : deleteUrlTemplate;
        var actionName = action === "restart" ? "重启" : "删除";
        requestJson(withHostUrl(template, hostId), {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCsrfToken(),
            },
            body: JSON.stringify({ cloud_id: getCloudId() }),
        })
            .then(function () {
                setNotice("success", "主机“" + hostId + "”" + actionName + "操作成功");
                return Promise.all([loadSummary(true), loadHosts(true)]);
            })
            .catch(function (error) {
                setNotice("error", error.message || (actionName + "失败"));
            });
    }

    function runHostActionByInput(action) {
        ensureHostsLoaded()
            .then(function () {
                var hostId = resolveHostId(hostActionInput && hostActionInput.value);
                if (hostActionInput) {
                    hostActionInput.value = hostId;
                }
                if (action === "restart") {
                    runHostAction("restart", hostId, "确认重启该主机吗？");
                } else {
                    runHostAction("delete", hostId, "删除后将无法恢复，确认继续吗？");
                }
            })
            .catch(function (error) {
                setNotice("error", error.message || "主机处理失败");
            });
    }

    function changeCredentialPassword() {
        var newPassword = passwordInput && passwordInput.value ? passwordInput.value.trim() : "";
        if (!newPassword) {
            setNotice("warning", "请输入新密码");
            return;
        }
        ensureHostsLoaded()
            .then(function () {
                var hostId = resolveHostId(passwordHostInput && passwordHostInput.value);
                return requestJson(credentialPasswordUrl, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": getCsrfToken(),
                    },
                    body: JSON.stringify({
                        hostId: hostId,
                        password: newPassword,
                        cloud_id: getCloudId(),
                    }),
                }).then(function () {
                    if (passwordHostInput) {
                        passwordHostInput.value = hostId;
                    }
                    if (passwordInput) {
                        passwordInput.value = "";
                    }
                    setNotice("success", "凭据密码修改成功（Host ID: " + hostId + "）");
                });
            })
            .catch(function (error) {
                setNotice("error", error.message || "修改密码失败");
            });
    }

    function refreshAll(forceRefresh) {
        updateExportLink();
        return Promise.all([loadSummary(forceRefresh), loadHosts(forceRefresh), loadOnlineCount()]);
    }

    if (tableBody) {
        tableBody.addEventListener("click", function (event) {
            var button = event.target.closest("button[data-action]");
            if (!button) {
                return;
            }
            var action = button.getAttribute("data-action");
            var hostId = button.getAttribute("data-host-id");
            if (action === "credentials") {
                viewCredentials(hostId);
                return;
            }
            if (action === "restart") {
                runHostAction("restart", hostId, "确认重启该主机吗？");
                return;
            }
            if (action === "delete") {
                runHostAction("delete", hostId, "删除后将无法恢复，确认继续吗？");
            }
        });
    }

    if (refreshBtn) {
        refreshBtn.addEventListener("click", function () {
            refreshAll(true);
        });
    }
    if (refreshTableBtn) {
        refreshTableBtn.addEventListener("click", function () {
            loadHosts(true);
        });
    }
    if (loadHostsBtn) {
        loadHostsBtn.addEventListener("click", function () {
            focusHostsList();
            loadHosts(true);
        });
    }
    if (pingBtn) {
        pingBtn.addEventListener("click", function () {
            requestJson(pingUrl)
                .then(function () {
                    setNotice("success", "JumpServer 连通性正常", 3000);
                })
                .catch(function (error) {
                    setNotice("error", error.message || "JumpServer 连通性检测失败");
                });
        });
    }
    if (searchInput) {
        searchInput.addEventListener("input", renderRows);
    }
    if (cloudIdInput) {
        cloudIdInput.addEventListener("change", function () {
            refreshAll(true);
        });
    }
    if (restartByInputBtn) {
        restartByInputBtn.addEventListener("click", function () {
            runHostActionByInput("restart");
        });
    }
    if (deleteByInputBtn) {
        deleteByInputBtn.addEventListener("click", function () {
            runHostActionByInput("delete");
        });
    }
    if (queryUserBtn) {
        queryUserBtn.addEventListener("click", queryUser);
    }
    if (addAuthBtn) {
        addAuthBtn.addEventListener("click", openAuthModal);
    }
    if (authSubmitBtn) {
        authSubmitBtn.addEventListener("click", addUserAuth);
    }
    if (authModalCloseBtn) {
        authModalCloseBtn.addEventListener("click", closeAuthModal);
    }
    if (authModalBackdrop) {
        authModalBackdrop.addEventListener("click", closeAuthModal);
    }
    if (authHostInput) {
        authHostInput.addEventListener("input", function () {
            state.authResolvedHostId = "";
            setAuthHostTip("", "", "");
            scheduleAuthHostResolve();
        });
        authHostInput.addEventListener("blur", function () {
            resolveAuthHostNow(true);
        });
        authHostInput.addEventListener("keydown", function (event) {
            if (event.key === "Enter" && authSubmitBtn) {
                event.preventDefault();
                authSubmitBtn.click();
            }
        });
    }
    if (authAccountInput) {
        authAccountInput.addEventListener("input", function () {
            state.authResolvedUserId = "";
            state.authResolvedUserInfo = null;
            setAuthUserTip("", "", "");
            scheduleAuthUserResolve();
        });
        authAccountInput.addEventListener("blur", function () {
            resolveAuthUserNow(true);
        });
        authAccountInput.addEventListener("keydown", function (event) {
            if (event.key === "Enter" && authSubmitBtn) {
                event.preventDefault();
                authSubmitBtn.click();
            }
        });
    }
    if (changePasswordBtn) {
        changePasswordBtn.addEventListener("click", changeCredentialPassword);
    }

    if (credentialModalCloseBtn) {
        credentialModalCloseBtn.addEventListener("click", closeCredentialModal);
    }
    if (credentialModalBackdrop) {
        credentialModalBackdrop.addEventListener("click", closeCredentialModal);
    }

    document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") {
            return;
        }
        if (authModal && !authModal.hidden) {
            closeAuthModal();
            return;
        }
        if (credentialModal && !credentialModal.hidden) {
            closeCredentialModal();
            return;
        }
    });

    updateExportLink();
    refreshAll(false);
})();
