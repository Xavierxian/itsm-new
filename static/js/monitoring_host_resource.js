(function () {
    var page = document.querySelector("[data-hostmon-page]");
    if (!page) {
        return;
    }

    var dataUrl = page.getAttribute("data-data-url") || "";
    var alertsUrl = page.getAttribute("data-alerts-url") || "";
    var targetsUrl = page.getAttribute("data-targets-url") || "";
    var refreshSeconds = Number(page.getAttribute("data-default-refresh-seconds") || "45");

    var thresholdInput = document.getElementById("hostmon-threshold");
    var refreshBtn = document.getElementById("hostmon-refresh-btn");
    var searchInput = document.getElementById("hostmon-search");
    var tableBody = document.getElementById("hostmon-table-body");
    var filterCards = document.querySelectorAll("[data-hostmon-filter]");
    var filterIndicator = document.getElementById("hostmon-filter-indicator");
    var sortButtons = document.querySelectorAll("[data-hostmon-sort-key]");

    var totalHostsNode = document.getElementById("hostmon-total-hosts");
    var alertHostsNode = document.getElementById("hostmon-alert-hosts");
    var totalAlertsNode = document.getElementById("hostmon-total-alerts");
    var targetHealthNode = document.getElementById("hostmon-target-health");
    var cpuOver80Node = document.getElementById("hostmon-cpu-over-80");
    var memoryOver80Node = document.getElementById("hostmon-memory-over-80");
    var rootOver80Node = document.getElementById("hostmon-root-over-80");
    var homeOver80Node = document.getElementById("hostmon-home-over-80");

    var alertList = document.getElementById("hostmon-alert-list");
    var targetList = document.getElementById("hostmon-target-list");
    var alertUpdatedAtNode = document.getElementById("hostmon-alert-updated-at");
    var targetUpdatedAtNode = document.getElementById("hostmon-target-updated-at");

    var noticeNode = document.getElementById("hostmon-notice");

    var state = {
        hosts: [],
        alerts: [],
        targets: [],
        sortKey: "",
        sortDirection: "desc",
        activeCardFilter: "",
    };

    var refreshTimer = null;
    var noticeTimer = null;

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function toNumber(value) {
        var num = Number(value);
        return Number.isFinite(num) ? num : null;
    }

    function formatNumber(value, digits) {
        if (value === null || value === undefined || value === "") {
            return "--";
        }
        var num = Number(value);
        if (!Number.isFinite(num)) {
            return "--";
        }
        return num.toFixed(typeof digits === "number" ? digits : 1);
    }

    function metricValue(metrics, key) {
        return toNumber(metrics ? metrics[key] : null);
    }

    function buildUrl(baseUrl, params) {
        var url = new URL(baseUrl, window.location.origin);
        Object.keys(params || {}).forEach(function (key) {
            var value = params[key];
            if (value === null || value === undefined || value === "") {
                return;
            }
            url.searchParams.set(key, String(value));
        });
        return url.pathname + url.search;
    }

    function requestJson(url, options) {
        return fetch(url, Object.assign({ credentials: "same-origin" }, options || {})).then(function (response) {
            return response
                .json()
                .catch(function () {
                    return { success: false, error: "响应格式错误" };
                })
                .then(function (payload) {
                    if (!response.ok || !payload.success) {
                        throw new Error(payload.error || payload.details || ("请求失败（HTTP " + response.status + "）"));
                    }
                    return payload;
                });
        });
    }

    function setNotice(type, message, autoHideMs) {
        if (!noticeNode) {
            return;
        }

        if (noticeTimer) {
            window.clearTimeout(noticeTimer);
            noticeTimer = null;
        }

        if (!message) {
            noticeNode.hidden = true;
            noticeNode.className = "hostmon-notice-v2";
            noticeNode.textContent = "";
            return;
        }

        noticeNode.hidden = false;
        noticeNode.textContent = message;
        noticeNode.className = "hostmon-notice-v2" + (type ? " is-" + type : "");

        var delay = typeof autoHideMs === "number" ? autoHideMs : 3500;
        if (delay > 0) {
            noticeTimer = window.setTimeout(function () {
                setNotice("", "");
            }, delay);
        }
    }

    function getThreshold() {
        var raw = thresholdInput && thresholdInput.value ? thresholdInput.value.trim() : "90";
        var value = Number(raw);
        if (!Number.isFinite(value)) {
            return 90;
        }
        if (value < 0) {
            return 0;
        }
        if (value > 100) {
            return 100;
        }
        return value;
    }

    function metricToneByPercent(value) {
        if (value === null) {
            return "na";
        }
        if (value >= 90) {
            return "danger";
        }
        if (value >= 80) {
            return "warning";
        }
        return "good";
    }

    function renderPercentCell(value) {
        if (value === null) {
            return '<span class="hostmon-metric-pill-v2 is-na">N/A</span>';
        }
        return '<span class="hostmon-metric-pill-v2 is-' + metricToneByPercent(value) + '">' + formatNumber(value, 2) + "%</span>";
    }

    function renderPlainMetric(value, digits) {
        if (value === null) {
            return '<span class="hostmon-metric-pill-v2 is-na">N/A</span>';
        }
        return '<span class="hostmon-number-v2">' + formatNumber(value, digits) + "</span>";
    }

    function renderUserCell(user) {
        var value = String(user || "").trim();
        if (!value) {
            value = "未知";
        }
        var tone = value === "未知" ? "na" : "normal";
        return '<span class="hostmon-user-pill-v2 is-' + tone + '">' + escapeHtml(value) + "</span>";
    }

    function normalize(value) {
        return String(value || "").toLowerCase();
    }

    function isAlertHostByThreshold(host, threshold) {
        var metrics = host.metrics || {};
        var rootUsage = metricValue(metrics, "root_usage");
        var dataUsage = metricValue(metrics, "data_usage");
        var homeUsage = metricValue(metrics, "home_usage");
        return (rootUsage !== null && rootUsage >= threshold) ||
            (dataUsage !== null && dataUsage >= threshold) ||
            (homeUsage !== null && homeUsage >= threshold);
    }

    function applyCardFilter(rows) {
        var filterKey = state.activeCardFilter;
        if (!filterKey) {
            return rows;
        }

        var threshold = getThreshold();
        return rows.filter(function (host) {
            var metrics = host.metrics || {};
            var cpuUsage = metricValue(metrics, "cpu_usage");
            var memoryUsage = metricValue(metrics, "memory_usage");
            var rootUsage = metricValue(metrics, "root_usage");
            var homeUsage = metricValue(metrics, "home_usage");

            if (filterKey === "cpu_over_80") {
                return cpuUsage !== null && cpuUsage > 80;
            }
            if (filterKey === "memory_over_80") {
                return memoryUsage !== null && memoryUsage > 80;
            }
            if (filterKey === "root_over_80") {
                return rootUsage !== null && rootUsage > 80;
            }
            if (filterKey === "home_over_80") {
                return homeUsage !== null && homeUsage > 80;
            }
            if (filterKey === "alert_hosts") {
                return isAlertHostByThreshold(host, threshold);
            }
            return true;
        });
    }

    function updateCardFilterUI() {
        if (filterCards && filterCards.length) {
            Array.prototype.forEach.call(filterCards, function (card) {
                var key = card.getAttribute("data-hostmon-filter") || "";
                card.classList.toggle("is-active", !!key && key === state.activeCardFilter);
            });
        }

        if (!filterIndicator) {
            return;
        }
        if (!state.activeCardFilter) {
            filterIndicator.hidden = true;
            filterIndicator.textContent = "";
            return;
        }

        var activeCard = document.querySelector('[data-hostmon-filter="' + state.activeCardFilter + '"]');
        var label = activeCard ? (activeCard.getAttribute("data-hostmon-filter-label") || "") : "";
        filterIndicator.hidden = false;
        filterIndicator.textContent = label ? ("当前筛选: " + label) : "当前筛选已启用";
    }

    function updateSortButtons() {
        if (!sortButtons || !sortButtons.length) {
            return;
        }
        Array.prototype.forEach.call(sortButtons, function (button) {
            var key = button.getAttribute("data-hostmon-sort-key") || "";
            var icon = button.querySelector(".hostmon-sort-icon-v2");
            var isActive = key && key === state.sortKey;

            button.classList.toggle("is-active", isActive);
            button.setAttribute("data-sort-direction", isActive ? state.sortDirection : "");

            if (icon) {
                if (!isActive) {
                    icon.textContent = "↕";
                } else if (state.sortDirection === "asc") {
                    icon.textContent = "↑";
                } else {
                    icon.textContent = "↓";
                }
            }
        });
    }

    function sortHosts(rows) {
        if (!state.sortKey) {
            return rows;
        }

        var direction = state.sortDirection === "asc" ? 1 : -1;
        var key = state.sortKey;
        var sorted = rows.slice();

        sorted.sort(function (a, b) {
            var aValue = metricValue(a.metrics || {}, key);
            var bValue = metricValue(b.metrics || {}, key);

            var aEmpty = aValue === null;
            var bEmpty = bValue === null;

            if (aEmpty && bEmpty) {
                return String(a.ip || "").localeCompare(String(b.ip || ""));
            }
            if (aEmpty) {
                return 1;
            }
            if (bEmpty) {
                return -1;
            }
            if (aValue === bValue) {
                return String(a.ip || "").localeCompare(String(b.ip || ""));
            }
            return (aValue - bValue) * direction;
        });

        return sorted;
    }

    function renderHostTable() {
        if (!tableBody) {
            return;
        }

        var keyword = normalize(searchInput && searchInput.value ? searchInput.value.trim() : "");
        var rows = state.hosts.filter(function (host) {
            if (!keyword) {
                return true;
            }
            var searchable = [host.instance, host.ip, host.os_type, host.department, host.applicant].join(" ").toLowerCase();
            return searchable.indexOf(keyword) >= 0;
        });
        rows = applyCardFilter(rows);
        rows = sortHosts(rows);

        if (!rows.length) {
            tableBody.innerHTML = '<tr><td colspan="16"><div class="empty-inline empty-inline-v4">没有匹配的主机</div></td></tr>';
            return;
        }

        tableBody.innerHTML = rows
            .map(function (host) {
                var metrics = host.metrics || {};

                var tcp = metricValue(metrics, "tcp_connections");
                var cpuCores = metricValue(metrics, "cpu_cores");
                var memoryGb = metricValue(metrics, "memory_gb");
                var diskGb = metricValue(metrics, "disk_gb");
                var uptimeDays = metricValue(metrics, "uptime_days");

                var cpuPercent = metricValue(metrics, "cpu_usage");
                var memPercent = metricValue(metrics, "memory_usage");
                var rootPercent = metricValue(metrics, "root_usage");
                var dataPercent = metricValue(metrics, "data_usage");
                var homePercent = metricValue(metrics, "home_usage");
                var xsPercent = metricValue(metrics, "xs_usage");
                var ioPercent = metricValue(metrics, "io_usage");
                var flow = metricValue(metrics, "network_mbps");

                return (
                    "<tr>" +
                    '<td class="hostmon-cell-ip"><code>' + escapeHtml(host.ip || "--") + "</code></td>" +
                    '<td class="hostmon-cell-user">' + renderUserCell(host.applicant || "未知") + "</td>" +
                    '<td class="hostmon-cell-os">' + escapeHtml(host.os_type || "--") + "</td>" +
                    '<td class="hostmon-cell-number">' + renderPlainMetric(tcp, 0) + "</td>" +
                    '<td class="hostmon-cell-number">' + renderPlainMetric(cpuCores, 0) + "</td>" +
                    '<td class="hostmon-cell-number">' + renderPlainMetric(memoryGb, 1) + "</td>" +
                    '<td class="hostmon-cell-number">' + renderPlainMetric(diskGb, 1) + "</td>" +
                    '<td class="hostmon-cell-number">' + renderPlainMetric(uptimeDays, 1) + "</td>" +
                    '<td class="hostmon-cell-number">' + renderPercentCell(cpuPercent) + "</td>" +
                    '<td class="hostmon-cell-number">' + renderPercentCell(memPercent) + "</td>" +
                    '<td class="hostmon-cell-number">' + renderPercentCell(rootPercent) + "</td>" +
                    '<td class="hostmon-cell-number">' + renderPercentCell(dataPercent) + "</td>" +
                    '<td class="hostmon-cell-number">' + renderPercentCell(homePercent) + "</td>" +
                    '<td class="hostmon-cell-number">' + renderPercentCell(xsPercent) + "</td>" +
                    '<td class="hostmon-cell-number">' + renderPercentCell(ioPercent) + "</td>" +
                    '<td class="hostmon-cell-flow">' + (flow === null ? '<span class="hostmon-metric-pill-v2 is-na">N/A</span>' : ('<span class="hostmon-number-v2">' + formatNumber(flow, 2) + ' MB</span>')) + "</td>" +
                    "</tr>"
                );
            })
            .join("");
    }

    function renderAlerts() {
        if (!alertList) {
            return;
        }

        if (!state.alerts.length) {
            alertList.innerHTML = '<div class="empty-inline empty-inline-v4">暂无分区告警</div>';
            return;
        }

        alertList.innerHTML = state.alerts
            .map(function (item) {
                var alertText = (item.alerts || [])
                    .map(function (entry) {
                        return escapeHtml(entry.metric_label) + " " + formatNumber(entry.value, 1) + "%";
                    })
                    .join(" · ");

                return (
                    '<article class="hostmon-alert-item-v2">' +
                    '<header><strong>' + escapeHtml(item.ip || item.instance || "未知") + "</strong><span>" + escapeHtml(item.applicant || "未知") + "</span></header>" +
                    '<p>' + alertText + "</p>" +
                    "</article>"
                );
            })
            .join("");
    }

    function renderTargets() {
        if (!targetList) {
            return;
        }

        if (!state.targets.length) {
            targetList.innerHTML = '<div class="empty-inline empty-inline-v4">暂无采集目标信息</div>';
            return;
        }

        targetList.innerHTML = state.targets
            .slice(0, 8)
            .map(function (target) {
                var tone = target.health === "up" ? "success" : "danger";
                var label = target.health === "up" ? "UP" : (target.health || "unknown").toUpperCase();
                return (
                    '<div class="hostmon-target-item-v2">' +
                    '<code>' + escapeHtml(target.endpoint || "--") + "</code>" +
                    '<span class="result-badge-v4 result-badge-v4-' + tone + '">' + label + "</span>" +
                    "</div>"
                );
            })
            .join("");
    }

    function nowText() {
        return new Date().toLocaleTimeString();
    }

    function updateSummary(dataPayload, alertsPayload, targetsPayload) {
        if (totalHostsNode) {
            totalHostsNode.textContent = String(dataPayload.total_hosts || 0);
        }
        if (alertHostsNode) {
            alertHostsNode.textContent = String(alertsPayload.total_hosts || 0);
        }
        if (totalAlertsNode) {
            totalAlertsNode.textContent = String(alertsPayload.total_alerts || 0);
        }
        if (targetHealthNode) {
            var total = Number(targetsPayload.total || 0);
            var healthy = Number(targetsPayload.healthy || 0);
            targetHealthNode.textContent = total ? (healthy + " / " + total) : "--";
        }
    }

    function updateThresholdCards() {
        var cpuCount = 0;
        var memoryCount = 0;
        var rootCount = 0;
        var homeCount = 0;

        state.hosts.forEach(function (host) {
            var metrics = host.metrics || {};
            var cpuUsage = metricValue(metrics, "cpu_usage");
            var memoryUsage = metricValue(metrics, "memory_usage");
            var rootUsage = metricValue(metrics, "root_usage");
            var homeUsage = metricValue(metrics, "home_usage");

            if (cpuUsage !== null && cpuUsage > 80) {
                cpuCount += 1;
            }
            if (memoryUsage !== null && memoryUsage > 80) {
                memoryCount += 1;
            }
            if (rootUsage !== null && rootUsage > 80) {
                rootCount += 1;
            }
            if (homeUsage !== null && homeUsage > 80) {
                homeCount += 1;
            }
        });

        if (cpuOver80Node) {
            cpuOver80Node.textContent = String(cpuCount);
        }
        if (memoryOver80Node) {
            memoryOver80Node.textContent = String(memoryCount);
        }
        if (rootOver80Node) {
            rootOver80Node.textContent = String(rootCount);
        }
        if (homeOver80Node) {
            homeOver80Node.textContent = String(homeCount);
        }
    }

    function loadSnapshot() {
        return requestJson(dataUrl).then(function (payload) {
            state.hosts = Array.isArray(payload.hosts) ? payload.hosts : [];
            renderHostTable();
            updateThresholdCards();
            return payload;
        });
    }

    function loadAlerts() {
        var threshold = getThreshold();
        var url = buildUrl(alertsUrl, { threshold: threshold });
        return requestJson(url).then(function (payload) {
            state.alerts = Array.isArray(payload.alerts) ? payload.alerts : [];
            renderAlerts();
            if (alertUpdatedAtNode) {
                alertUpdatedAtNode.textContent = nowText();
            }
            return payload;
        });
    }

    function loadTargets() {
        return requestJson(targetsUrl).then(function (payload) {
            state.targets = Array.isArray(payload.targets) ? payload.targets : [];
            renderTargets();
            if (targetUpdatedAtNode) {
                targetUpdatedAtNode.textContent = nowText();
            }
            return payload;
        });
    }

    function refreshAll(showToast) {
        return Promise.all([loadSnapshot(), loadAlerts(), loadTargets()])
            .then(function (results) {
                var dataPayload = results[0] || {};
                var alertsPayload = results[1] || {};
                var targetsPayload = results[2] || {};

                updateSummary(dataPayload, alertsPayload, targetsPayload);

                var warnings = Array.isArray(dataPayload.errors) ? dataPayload.errors : [];
                if (warnings.length) {
                    setNotice("warning", "部分指标查询失败: " + warnings.slice(0, 2).join("；"), 5000);
                } else if (showToast) {
                    setNotice("success", "监控数据已更新");
                }
            })
            .catch(function (error) {
                setNotice("error", error.message || "刷新失败");
            });
    }

    if (refreshBtn) {
        refreshBtn.addEventListener("click", function () {
            refreshAll(true);
        });
    }

    if (searchInput) {
        searchInput.addEventListener("input", renderHostTable);
    }

    if (thresholdInput) {
        thresholdInput.addEventListener("change", function () {
            renderHostTable();
            loadAlerts()
                .then(function (payload) {
                    if (alertHostsNode) {
                        alertHostsNode.textContent = String(payload.total_hosts || 0);
                    }
                    if (totalAlertsNode) {
                        totalAlertsNode.textContent = String(payload.total_alerts || 0);
                    }
                })
                .catch(function (error) {
                    setNotice("error", error.message || "告警刷新失败");
                });
        });
    }

    if (filterCards && filterCards.length) {
        Array.prototype.forEach.call(filterCards, function (card) {
            card.addEventListener("click", function () {
                var key = card.getAttribute("data-hostmon-filter") || "";
                if (!key) {
                    return;
                }
                if (state.activeCardFilter === key) {
                    state.activeCardFilter = "";
                } else {
                    state.activeCardFilter = key;
                }
                updateCardFilterUI();
                renderHostTable();
            });
        });
    }

    if (sortButtons && sortButtons.length) {
        Array.prototype.forEach.call(sortButtons, function (button) {
            button.addEventListener("click", function () {
                var key = button.getAttribute("data-hostmon-sort-key") || "";
                if (!key) {
                    return;
                }

                if (state.sortKey === key) {
                    state.sortDirection = state.sortDirection === "desc" ? "asc" : "desc";
                } else {
                    state.sortKey = key;
                    state.sortDirection = "desc";
                }
                updateSortButtons();
                renderHostTable();
            });
        });
    }

    updateSortButtons();
    updateCardFilterUI();

    refreshAll(false);

    if (refreshSeconds > 0) {
        refreshTimer = window.setInterval(function () {
            refreshAll(false);
        }, refreshSeconds * 1000);
    }
})();
