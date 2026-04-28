(function () {
    var panel = document.querySelector("[data-dashboard-monitor]");
    if (!panel) {
        return;
    }

    var alertsUrl = panel.getAttribute("data-alerts-url") || "";
    var mailUrl = panel.getAttribute("data-mail-url") || "";
    var threshold = Number(panel.getAttribute("data-threshold") || "90");
    var refreshSeconds = Number(panel.getAttribute("data-refresh-seconds") || "45");
    var trendDataNode = document.getElementById("dashboard-bsecp-trend-data");
    var trendRaw = trendDataNode ? (trendDataNode.textContent || "{}") : "{}";

    var chartWrapNode = document.querySelector(".dashboard-auth-chart-wrap-v3");
    var canvasNode = document.getElementById("dashboard-bsecp-auth-chart");
    var chartEmptyNode = document.getElementById("dashboard-bsecp-auth-empty");
    var chartTooltipNode = document.getElementById("dashboard-bsecp-auth-tooltip");
    var rangeButtons = Array.prototype.slice.call(document.querySelectorAll("[data-bsecp-range]"));

    var alertTimeNode = document.getElementById("dashboard-monitor-alert-time");
    var alertListNode = document.getElementById("dashboard-monitor-alert-list");
    var refreshBtn = document.getElementById("dashboard-monitor-refresh-btn");
    var mailBtn = document.getElementById("dashboard-monitor-mail-btn");

    var trendPayload = parseTrendPayload(trendRaw);
    var trendSeries = normalizeTrendSeries(Array.isArray(trendPayload.series) ? trendPayload.series : []);
    var trendPeriods = normalizeTrendPeriods(trendPayload.periods);
    var latestAlerts = [];
    var mailSending = false;

    var state = {
        activeRange: "week",
        hoverIndex: -1,
        model: null,
    };

    if (mailBtn) {
        mailBtn.disabled = true;
    }

    function parseJsonSafe(text, fallback) {
        try {
            return JSON.parse(text);
        } catch (error) {
            return fallback;
        }
    }

    function parseTrendPayload(rawText) {
        var payload = parseJsonSafe(rawText, null);
        if (payload && typeof payload === "object") {
            return payload;
        }
        return {};
    }

    function toNonNegativeInt(value) {
        var num = Number(value);
        if (!Number.isFinite(num) || num < 0) {
            return 0;
        }
        return Math.round(num);
    }

    function normalizeTrendSeries(rows) {
        var mapped = rows
            .map(function (row) {
                return {
                    date: String((row && row.date) || ""),
                    success: toNonNegativeInt(row && row.success),
                    failure: toNonNegativeInt(row && row.failure),
                    pending: toNonNegativeInt(row && row.pending),
                };
            })
            .filter(function (row) {
                return /^\d{4}-\d{2}-\d{2}$/.test(row.date);
            });

        mapped.sort(function (a, b) {
            return a.date < b.date ? -1 : a.date > b.date ? 1 : 0;
        });

        return mapped;
    }

    function normalizeTrendPeriods(periods) {
        var source = periods && typeof periods === "object" ? periods : {};
        return {
            week: Math.max(1, toNonNegativeInt(source.week) || 7),
            half_month: Math.max(1, toNonNegativeInt(source.half_month) || 15),
            month: Math.max(1, toNonNegativeInt(source.month) || 30),
        };
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatNumber(value, digits) {
        var num = Number(value);
        if (!Number.isFinite(num)) {
            return "--";
        }
        return num.toFixed(typeof digits === "number" ? digits : 1);
    }

    function nowText() {
        return new Date().toLocaleString();
    }

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function formatDateLabel(dateText) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(dateText)) {
            return dateText || "--";
        }
        return dateText.slice(5);
    }

    function getCookie(name) {
        var prefix = name + "=";
        var decoded = decodeURIComponent(document.cookie || "");
        var parts = decoded.split(";");
        for (var i = 0; i < parts.length; i += 1) {
            var item = parts[i].trim();
            if (item.indexOf(prefix) === 0) {
                return item.substring(prefix.length);
            }
        }
        return "";
    }

    function requestJson(url, options) {
        var requestOptions = Object.assign({ credentials: "same-origin" }, options || {});
        return fetch(url, requestOptions).then(function (response) {
            return response
                .json()
                .catch(function () {
                    return { success: false, error: "Invalid response format" };
                })
                .then(function (payload) {
                    if (!response.ok || !payload.success) {
                        throw new Error(payload.error || payload.details || ("Request failed (HTTP " + response.status + ")"));
                    }
                    return payload;
                });
        });
    }

    function postJson(url, payload) {
        var headers = {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        };
        var csrfToken = getCookie("csrftoken");
        if (csrfToken) {
            headers["X-CSRFToken"] = csrfToken;
        }
        return requestJson(url, {
            method: "POST",
            headers: headers,
            body: JSON.stringify(payload || {}),
        });
    }

    function getVisibleTrendRows() {
        var days = trendPeriods[state.activeRange] || trendPeriods.week;
        if (!trendSeries.length) {
            return [];
        }
        if (trendSeries.length <= days) {
            return trendSeries.slice();
        }
        return trendSeries.slice(trendSeries.length - days);
    }

    function buildYAxis(maxValue) {
        if (!Number.isFinite(maxValue) || maxValue <= 0) {
            return { max: 6, step: 1, ticks: 6 };
        }

        var ticks = 6;
        var roughStep = maxValue / ticks;
        var magnitude = Math.pow(10, Math.floor(Math.log(roughStep) / Math.LN10));
        var normalized = roughStep / magnitude;
        var steps = [1, 2, 2.5, 5, 10];
        var normalizedStep = steps[steps.length - 1];

        for (var i = 0; i < steps.length; i += 1) {
            if (normalized <= steps[i]) {
                normalizedStep = steps[i];
                break;
            }
        }

        var step = normalizedStep * magnitude;
        var max = step * ticks;
        while (max < maxValue) {
            max += step;
        }

        return {
            max: max,
            step: step,
            ticks: ticks,
        };
    }

    function chartXForIndex(model, index) {
        if (model.count <= 1) {
            return model.padding.left + model.plotWidth / 2;
        }
        return model.padding.left + (model.plotWidth * index) / (model.count - 1);
    }

    function chartYForValue(model, value) {
        var num = Number(value);
        if (!Number.isFinite(num)) {
            return null;
        }
        var ratio = model.axis.max === 0 ? 0 : num / model.axis.max;
        ratio = clamp(ratio, 0, 1);
        return model.padding.top + model.plotHeight - ratio * model.plotHeight;
    }

    function buildPoints(model, fieldName) {
        var points = [];
        for (var i = 0; i < model.count; i += 1) {
            var row = model.rows[i];
            points.push({
                x: chartXForIndex(model, i),
                y: chartYForValue(model, row[fieldName]),
                index: i,
                value: row[fieldName],
            });
        }
        return points;
    }

    function drawSmoothPath(ctx, points, minY, maxY) {
        if (!points.length) {
            return;
        }

        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);

        if (points.length === 1) {
            ctx.lineTo(points[0].x + 0.01, points[0].y);
            return;
        }

        var tension = 0.5;
        for (var i = 0; i < points.length - 1; i += 1) {
            var p0 = i > 0 ? points[i - 1] : points[i];
            var p1 = points[i];
            var p2 = points[i + 1];
            var p3 = i + 2 < points.length ? points[i + 2] : p2;

            var cp1x = p1.x + ((p2.x - p0.x) / 6) * tension;
            var cp1y = p1.y + ((p2.y - p0.y) / 6) * tension;
            var cp2x = p2.x - ((p3.x - p1.x) / 6) * tension;
            var cp2y = p2.y - ((p3.y - p1.y) / 6) * tension;

            var segmentMinY = Math.min(p1.y, p2.y);
            var segmentMaxY = Math.max(p1.y, p2.y);
            cp1y = clamp(cp1y, segmentMinY, segmentMaxY);
            cp2y = clamp(cp2y, segmentMinY, segmentMaxY);
            cp1y = clamp(cp1y, minY, maxY);
            cp2y = clamp(cp2y, minY, maxY);

            ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
        }
    }

    function drawSeries(ctx, model, points, color, fillColor) {
        if (!points.length) {
            return;
        }

        var baselineY = model.padding.top + model.plotHeight;
        if (fillColor) {
            ctx.save();
            drawSmoothPath(ctx, points, model.padding.top, baselineY);
            ctx.lineTo(points[points.length - 1].x, baselineY);
            ctx.lineTo(points[0].x, baselineY);
            ctx.closePath();
            ctx.fillStyle = fillColor;
            ctx.fill();
            ctx.restore();
        }

        ctx.save();
        drawSmoothPath(ctx, points, model.padding.top, baselineY);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.6;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.stroke();
        ctx.restore();
    }

    function hideTrendTooltip() {
        if (chartTooltipNode) {
            chartTooltipNode.hidden = true;
        }
        state.hoverIndex = -1;
    }

    function showTrendTooltip(index) {
        if (!chartTooltipNode || !state.model || !chartWrapNode) {
            return;
        }
        if (index < 0 || index >= state.model.count) {
            hideTrendTooltip();
            return;
        }

        var row = state.model.rows[index];
        var x = chartXForIndex(state.model, index);
        var ys = [
            chartYForValue(state.model, row.success),
            chartYForValue(state.model, row.failure),
            chartYForValue(state.model, row.pending),
        ].filter(function (value) {
            return typeof value === "number";
        });

        var anchorY = state.model.padding.top + 20;
        if (ys.length) {
            anchorY = Math.max(state.model.padding.top + 12, Math.min.apply(null, ys) - 22);
        }

        chartTooltipNode.innerHTML =
            '<strong>' + escapeHtml(row.date) + '</strong>' +
            '<div><i class="is-success"></i>\u6388\u6743\u6210\u529f: ' + escapeHtml(String(row.success)) + '</div>' +
            '<div><i class="is-failure"></i>\u6388\u6743\u5931\u8d25: ' + escapeHtml(String(row.failure)) + '</div>' +
            '<div><i class="is-pending"></i>\u5f85\u5904\u7406: ' + escapeHtml(String(row.pending)) + '</div>';
        chartTooltipNode.hidden = false;

        var wrapWidth = chartWrapNode.clientWidth || state.model.width;
        var wrapHeight = chartWrapNode.clientHeight || state.model.height;
        var canvasOffsetLeft = canvasNode ? canvasNode.offsetLeft : 0;
        var canvasOffsetTop = canvasNode ? canvasNode.offsetTop : 0;
        var tooltipWidth = chartTooltipNode.offsetWidth || 170;
        var tooltipHeight = chartTooltipNode.offsetHeight || 100;

        var left = canvasOffsetLeft + x + 14;
        var top = canvasOffsetTop + anchorY + 12;

        if (left + tooltipWidth > wrapWidth - 8) {
            left = canvasOffsetLeft + x - tooltipWidth - 14;
        }
        if (top + tooltipHeight > wrapHeight - 8) {
            top = canvasOffsetTop + anchorY - tooltipHeight - 12;
        }
        left = Math.max(8, left);
        top = Math.max(8, top);

        chartTooltipNode.style.left = left + "px";
        chartTooltipNode.style.top = top + "px";
    }

    function drawTrendChart() {
        if (!canvasNode || !chartWrapNode) {
            return;
        }

        var rows = getVisibleTrendRows();
        var ctx = canvasNode.getContext("2d");
        if (!ctx) {
            return;
        }

        var width = Math.max(canvasNode.clientWidth || chartWrapNode.clientWidth || 320, 320);
        var height = Math.max(canvasNode.clientHeight || Number(canvasNode.getAttribute("height") || 320), 220);
        var dpr = window.devicePixelRatio || 1;

        canvasNode.width = Math.round(width * dpr);
        canvasNode.height = Math.round(height * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);

        if (!rows.length) {
            state.model = null;
            if (chartEmptyNode) {
                chartEmptyNode.hidden = false;
            }
            hideTrendTooltip();
            return;
        }

        if (chartEmptyNode) {
            chartEmptyNode.hidden = true;
        }

        var maxValue = 0;
        rows.forEach(function (row) {
            maxValue = Math.max(maxValue, row.success, row.failure, row.pending);
        });

        var axis = buildYAxis(maxValue);
        state.model = {
            rows: rows,
            count: rows.length,
            width: width,
            height: height,
            padding: { left: 44, right: 14, top: 18, bottom: 38 },
            axis: axis,
        };
        state.model.plotWidth = state.model.width - state.model.padding.left - state.model.padding.right;
        state.model.plotHeight = state.model.height - state.model.padding.top - state.model.padding.bottom;

        var model = state.model;
        ctx.strokeStyle = "#dbe5f2";
        ctx.lineWidth = 1;
        ctx.fillStyle = "#7086a2";
        ctx.font = "12px sans-serif";

        for (var i = 0; i <= axis.ticks; i += 1) {
            var y = model.padding.top + (model.plotHeight * i) / axis.ticks;
            var value = Math.max(0, axis.max - axis.step * i);
            ctx.beginPath();
            ctx.moveTo(model.padding.left, y);
            ctx.lineTo(model.width - model.padding.right, y);
            ctx.stroke();
            ctx.fillText(axis.step < 1 ? value.toFixed(1) : String(Math.round(value * 100) / 100), 8, y + 4);
        }

        var successPoints = buildPoints(model, "success");
        var failurePoints = buildPoints(model, "failure");
        var pendingPoints = buildPoints(model, "pending");

        drawSeries(ctx, model, successPoints, "#25b466", "rgba(37, 180, 102, 0.12)");
        drawSeries(ctx, model, failurePoints, "#ef4a4a", "rgba(239, 74, 74, 0.08)");
        drawSeries(ctx, model, pendingPoints, "#f39a14", "");

        if (state.hoverIndex >= 0 && state.hoverIndex < model.count) {
            var selectedX = chartXForIndex(model, state.hoverIndex);
            ctx.save();
            ctx.strokeStyle = "rgba(47, 97, 167, 0.45)";
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            ctx.moveTo(selectedX, model.padding.top);
            ctx.lineTo(selectedX, model.height - model.padding.bottom);
            ctx.stroke();
            ctx.restore();

            var hoverRow = model.rows[state.hoverIndex];
            [
                { y: chartYForValue(model, hoverRow.success), color: "#25b466" },
                { y: chartYForValue(model, hoverRow.failure), color: "#ef4a4a" },
                { y: chartYForValue(model, hoverRow.pending), color: "#f39a14" },
            ].forEach(function (item) {
                if (item.y === null) {
                    return;
                }
                ctx.fillStyle = item.color;
                ctx.beginPath();
                ctx.arc(selectedX, item.y, 5, 0, Math.PI * 2);
                ctx.fill();
                ctx.strokeStyle = "#ffffff";
                ctx.lineWidth = 2;
                ctx.stroke();
            });
        }

        ctx.fillStyle = "#667d99";
        ctx.font = "12px sans-serif";
        var labelIndexes = [0, Math.floor((model.count - 1) / 2), model.count - 1];
        var printed = {};
        labelIndexes.forEach(function (idx) {
            if (idx < 0 || idx >= model.count || printed[idx]) {
                return;
            }
            printed[idx] = true;
            var labelX = chartXForIndex(model, idx);
            var label = formatDateLabel(model.rows[idx].date);
            var textWidth = ctx.measureText(label).width;
            var textX = clamp(labelX - textWidth / 2, model.padding.left, model.width - model.padding.right - textWidth);
            ctx.fillText(label, textX, model.height - 10);
        });

        if (state.hoverIndex >= 0 && state.hoverIndex < model.count) {
            showTrendTooltip(state.hoverIndex);
        }
    }

    function updateHoverFromEvent(event) {
        if (!state.model || !chartWrapNode || !canvasNode) {
            hideTrendTooltip();
            return;
        }

        var canvasRect = canvasNode.getBoundingClientRect();
        if (
            event.clientX < canvasRect.left ||
            event.clientX > canvasRect.right ||
            event.clientY < canvasRect.top ||
            event.clientY > canvasRect.bottom
        ) {
            hideTrendTooltip();
            drawTrendChart();
            return;
        }

        var ratioX = canvasRect.width > 0 ? state.model.width / canvasRect.width : 1;
        var localX = (event.clientX - canvasRect.left) * ratioX;
        var bestIndex = 0;
        var bestDistance = Number.POSITIVE_INFINITY;

        for (var i = 0; i < state.model.count; i += 1) {
            var pointX = chartXForIndex(state.model, i);
            var distance = Math.abs(pointX - localX);
            if (distance < bestDistance) {
                bestDistance = distance;
                bestIndex = i;
            }
        }

        if (state.hoverIndex !== bestIndex) {
            state.hoverIndex = bestIndex;
            drawTrendChart();
        } else {
            showTrendTooltip(bestIndex);
        }
    }

    function bindTrendEvents() {
        if (!chartWrapNode) {
            return;
        }

        chartWrapNode.addEventListener("mousemove", updateHoverFromEvent);
        chartWrapNode.addEventListener("pointermove", updateHoverFromEvent);
        chartWrapNode.addEventListener("mouseleave", function () {
            hideTrendTooltip();
            drawTrendChart();
        });
        chartWrapNode.addEventListener("pointerleave", function () {
            hideTrendTooltip();
            drawTrendChart();
        });

        document.addEventListener("mousemove", function (event) {
            if (!chartTooltipNode || chartTooltipNode.hidden || !chartWrapNode) {
                return;
            }
            var rect = chartWrapNode.getBoundingClientRect();
            if (
                event.clientX < rect.left ||
                event.clientX > rect.right ||
                event.clientY < rect.top ||
                event.clientY > rect.bottom
            ) {
                hideTrendTooltip();
                drawTrendChart();
            }
        }, true);
    }

    function setActiveRange(nextRange) {
        if (!trendPeriods[nextRange]) {
            return;
        }
        state.activeRange = nextRange;
        state.hoverIndex = -1;
        updateRangeButtons();
        hideTrendTooltip();
        drawTrendChart();
    }

    function updateRangeButtons() {
        rangeButtons.forEach(function (button) {
            var range = button.getAttribute("data-bsecp-range") || "";
            var active = range === state.activeRange;
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-selected", active ? "true" : "false");
        });
    }

    function bindRangeEvents() {
        rangeButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                setActiveRange(button.getAttribute("data-bsecp-range") || "week");
            });
        });
    }

    function renderAlerts(alerts) {
        if (!alertListNode) {
            return;
        }

        latestAlerts = Array.isArray(alerts) ? alerts : [];
        if (mailBtn) {
            mailBtn.disabled = !latestAlerts.length || mailSending;
        }

        if (!latestAlerts.length) {
            alertListNode.innerHTML = '<div class="empty-inline empty-inline-v4">\u6682\u65e0\u5206\u533a\u544a\u8b66</div>';
            return;
        }

        alertListNode.innerHTML = latestAlerts
            .slice(0, 10)
            .map(function (item) {
                var entries = Array.isArray(item.alerts) ? item.alerts : [];
                var rootAlert = entries.find(function (entry) {
                    return entry.metric_key === "root_usage";
                }) || entries[0];
                var tags = entries
                    .slice(0, 3)
                    .map(function (entry) {
                        return '<span class="dashboard-alert-tag-v3">' + escapeHtml(entry.metric_label || entry.metric_key || "\u5206\u533a") + ': ' + formatNumber(entry.value, 1) + '%</span>';
                    })
                    .join('');

                return (
                    '<article class="dashboard-alert-item-v3">' +
                    '<header class="dashboard-alert-item-head-v3">' +
                    '<strong>' + escapeHtml(item.ip || item.instance || "\u672a\u77e5\u4e3b\u673a") + '</strong>' +
                    '<span class="dashboard-alert-count-v3">' + escapeHtml(String(entries.length)) + ' \u4e2a\u544a\u8b66</span>' +
                    '</header>' +
                    '<p class="dashboard-alert-item-meta-v3">' +
                    escapeHtml(item.os_type || "\u672a\u77e5") + ' | ' + escapeHtml(item.applicant || "\u672a\u77e5") + ' | ' + escapeHtml(item.department || "\u672a\u77e5") +
                    '</p>' +
                    '<div class="dashboard-alert-tags-v3">' +
                    tags +
                    (rootAlert ? '<span class="dashboard-alert-tag-v3 is-root">ROOT\u5206\u533a: ' + formatNumber(rootAlert.value, 1) + '%</span>' : '') +
                    '</div>' +
                    '</article>'
                );
            })
            .join('');
    }

    function buildMailBody(alerts) {
        var lines = ["\u7cfb\u7edf\u6982\u89c8\u9875\u5206\u533a\u544a\u8b66\u901a\u77e5", "", "\u65f6\u95f4: " + nowText(), ""];
        alerts.slice(0, 10).forEach(function (item, index) {
            var entries = Array.isArray(item.alerts) ? item.alerts : [];
            var metricSummary = entries
                .map(function (entry) {
                    return (entry.metric_label || entry.metric_key || "\u5206\u533a") + " " + formatNumber(entry.value, 1) + "%";
                })
                .join("; ");
            lines.push((index + 1) + ". " + (item.ip || item.instance || "\u672a\u77e5\u4e3b\u673a") + " | " + (item.os_type || "\u672a\u77e5") + " | " + (item.applicant || "\u672a\u77e5") + " | " + (item.department || "\u672a\u77e5"));
            lines.push("   " + (metricSummary || "\u65e0\u8be6\u7ec6\u6307\u6807"));
        });
        return lines.join("\n");
    }

    function loadAlerts() {
        if (!alertsUrl) {
            return Promise.resolve();
        }

        var queryUrl = new URL(alertsUrl, window.location.origin);
        queryUrl.searchParams.set("threshold", String(threshold));

        return requestJson(queryUrl.pathname + queryUrl.search)
            .then(function (payload) {
                renderAlerts(Array.isArray(payload.alerts) ? payload.alerts : []);
                if (alertTimeNode) {
                    alertTimeNode.textContent = nowText();
                }
            })
            .catch(function (error) {
                if (alertListNode) {
                    alertListNode.innerHTML = '<div class="empty-inline empty-inline-v4">' + escapeHtml(error.message || "\u544a\u8b66\u52a0\u8f7d\u5931\u8d25") + "</div>";
                }
                if (mailBtn) {
                    mailBtn.disabled = true;
                }
            });
    }

    function bindAlertEvents() {
        if (refreshBtn) {
            refreshBtn.addEventListener("click", function () {
                loadAlerts();
            });
        }

        if (mailBtn) {
            mailBtn.addEventListener("click", function () {
                if (!latestAlerts.length || mailSending) {
                    return;
                }
                if (!mailUrl) {
                    window.alert("\u672a\u914d\u7f6e\u90ae\u4ef6\u901a\u77e5\u63a5\u53e3\uff0c\u8bf7\u8054\u7cfb\u7ba1\u7406\u5458\u3002");
                    return;
                }

                var originalLabel = mailBtn.textContent;
                mailSending = true;
                mailBtn.disabled = true;
                mailBtn.textContent = "\u53d1\u9001\u4e2d...";

                postJson(mailUrl, { threshold: threshold })
                    .then(function (payload) {
                        window.alert((payload && payload.message) || "\u90ae\u4ef6\u53d1\u9001\u6210\u529f");
                    })
                    .catch(function (error) {
                        window.alert(error.message || "\u90ae\u4ef6\u53d1\u9001\u5931\u8d25");
                    })
                    .then(function () {
                        mailSending = false;
                        mailBtn.disabled = !latestAlerts.length;
                        mailBtn.textContent = originalLabel;
                    });
            });
        }
    }

    function debounce(fn, wait) {
        var timer = null;
        return function () {
            var args = arguments;
            clearTimeout(timer);
            timer = setTimeout(function () {
                fn.apply(null, args);
            }, wait);
        };
    }

    bindRangeEvents();
    bindTrendEvents();
    bindAlertEvents();
    updateRangeButtons();
    hideTrendTooltip();
    drawTrendChart();
    loadAlerts();

    window.addEventListener("resize", debounce(function () {
        hideTrendTooltip();
        drawTrendChart();
    }, 120));

    if (refreshSeconds > 0) {
        window.setInterval(loadAlerts, refreshSeconds * 1000);
    }
})();
