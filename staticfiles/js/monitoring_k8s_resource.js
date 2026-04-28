(function () {
    var page = document.querySelector("[data-k8smon-page]");
    if (!page) {
        return;
    }

    var summaryUrl = page.getAttribute("data-summary-url") || "";
    var namespacesUrl = page.getAttribute("data-namespaces-url") || "";
    var nodesUrl = page.getAttribute("data-nodes-url") || "";
    var trendUrlTemplate = page.getAttribute("data-trend-url-template") || "";
    var nodeTrendUrlTemplate = page.getAttribute("data-node-trend-url-template") || "";
    var aiStreamUrlTemplate = page.getAttribute("data-ai-stream-url-template") || "";
    var nodeAiStreamUrlTemplate = page.getAttribute("data-node-ai-stream-url-template") || "";
    var defaultRefreshSeconds = Number(page.getAttribute("data-default-refresh-seconds") || "60");
    var defaultTrendHours = Number(page.getAttribute("data-default-trend-hours") || "24");

    var refreshBtn = document.getElementById("k8smon-refresh-btn");
    var refreshIntervalInput = document.getElementById("k8smon-refresh-interval");
    var searchInput = document.getElementById("k8smon-search");
    var trendHoursInput = document.getElementById("k8smon-trend-hours");
    var noticeNode = document.getElementById("k8smon-notice");

    var namespaceBody = document.getElementById("k8smon-namespace-tbody");
    var nodeBody = document.getElementById("k8smon-node-tbody");
    var sortButtons = document.querySelectorAll("[data-k8smon-sort-key]");

    var totalCpuNode = document.getElementById("k8smon-total-cpu");
    var totalMemNode = document.getElementById("k8smon-total-mem");
    var totalNodesNode = document.getElementById("k8smon-total-nodes");
    var totalNamespacesNode = document.getElementById("k8smon-total-namespaces");
    var totalPodsNode = document.getElementById("k8smon-total-pods");
    var usedCpuTotalNode = document.getElementById("k8smon-used-cpu-total");
    var usedMemTotalNode = document.getElementById("k8smon-used-mem-total");
    var updatedAtNode = document.getElementById("k8smon-updated-at");
    var namespaceCountNode = document.getElementById("k8smon-namespace-count");
    var nodeCountNode = document.getElementById("k8smon-node-count");

    var trendTitleNode = document.getElementById("k8smon-trend-title");
    var trendSubtitleNode = document.getElementById("k8smon-trend-subtitle");
    var trendCanvas = document.getElementById("k8smon-trend-canvas");
    var trendChartWrapNode = trendCanvas ? trendCanvas.parentElement : null;
    var trendTooltipNode = document.getElementById("k8smon-trend-tooltip");
    var trendEmptyNode = document.getElementById("k8smon-trend-empty");
    var aiResultNode = document.getElementById("k8smon-ai-result");

    var nodeModal = document.getElementById("k8smon-node-modal");
    var nodeModalTitleNode = document.getElementById("k8smon-node-modal-title");
    var nodeModalSubtitleNode = document.getElementById("k8smon-node-modal-subtitle");
    var nodeTrendHoursInput = document.getElementById("k8smon-node-trend-hours");
    var nodeTrendCanvas = document.getElementById("k8smon-node-trend-canvas");
    var nodeTrendChartWrapNode = nodeTrendCanvas ? nodeTrendCanvas.parentElement : null;
    var nodeTrendTooltipNode = document.getElementById("k8smon-node-trend-tooltip");
    var nodeTrendEmptyNode = document.getElementById("k8smon-node-trend-empty");
    var nodeAiResultNode = document.getElementById("k8smon-node-ai-result");
    var nodeModalCloseTriggers = nodeModal ? nodeModal.querySelectorAll("[data-k8smon-node-close]") : [];

    var state = {
        summary: null,
        namespaces: [],
        nodes: [],
        selectedNamespace: "",
        sortKey: "k8s_namespace_cpu_per",
        sortDirection: "desc",
        trendData: null,
        chartModel: null,
        hoverIndex: -1,
        trendPreviewIndex: -1,
        trendPreviewX: -1,
        refreshSeconds: Number.isFinite(defaultRefreshSeconds) && defaultRefreshSeconds > 0 ? defaultRefreshSeconds : 60,
        aiBusy: false,
        aiAbortController: null,
        aiSignature: "",
        aiStreamText: "",
        aiPendingText: "",
        aiTypingTimer: null,
        aiFinalizeText: null,
        nodeModalOpen: false,
        selectedNodeIp: "",
        nodeTrendData: null,
        nodeTrendChartModel: null,
        nodeTrendHoverIndex: -1,
        nodeTrendPreviewIndex: -1,
        nodeTrendPreviewX: -1,
        nodeAiBusy: false,
        nodeAiAbortController: null,
        nodeAiSignature: "",
        nodeAiStreamText: "",
        nodeAiPendingText: "",
        nodeAiTypingTimer: null,
        nodeAiFinalizeText: null,
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
        var num = toNumber(value);
        if (num === null) {
            return "--";
        }
        return num.toFixed(typeof digits === "number" ? digits : 1);
    }

    function requestJson(url, options) {
        var requestOptions = options && typeof options === "object" ? options : {};
        requestOptions.credentials = "same-origin";
        return fetch(url, requestOptions).then(function (response) {
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
        noticeNode.className = "hostmon-notice-v2" + (type ? " is-" + type : "");
        noticeNode.textContent = message;
        var delay = typeof autoHideMs === "number" ? autoHideMs : 3500;
        if (delay > 0) {
            noticeTimer = window.setTimeout(function () {
                setNotice("", "");
            }, delay);
        }
    }

    function metricPill(value) {
        var num = toNumber(value);
        if (num === null) {
            return '<span class="hostmon-metric-pill-v2 is-na">N/A</span>';
        }
        var tone = "good";
        if (num >= 90) {
            tone = "danger";
        } else if (num >= 80) {
            tone = "warning";
        }
        return '<span class="hostmon-metric-pill-v2 is-' + tone + '">' + formatNumber(num, 2) + "%</span>";
    }

    function formatTextTime(value) {
        var text = String(value || "").trim();
        if (!text) {
            return "--";
        }
        var m = text.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
        if (m) {
            return m[2] + "-" + m[3] + " " + m[4] + ":" + m[5];
        }
        var normalized = text.replace(" ", "T");
        var date = new Date(normalized);
        if (!Number.isNaN(date.getTime())) {
            var mm = String(date.getMonth() + 1).padStart(2, "0");
            var dd = String(date.getDate()).padStart(2, "0");
            var hh = String(date.getHours()).padStart(2, "0");
            var mi = String(date.getMinutes()).padStart(2, "0");
            return mm + "-" + dd + " " + hh + ":" + mi;
        }
        return text.length > 16 ? text.slice(0, 16) : text;
    }

    function updateSortButtons() {
        Array.prototype.forEach.call(sortButtons || [], function (button) {
            var key = button.getAttribute("data-k8smon-sort-key") || "";
            var icon = button.querySelector(".k8smon-sort-icon-v2");
            var active = key && key === state.sortKey;
            button.classList.toggle("is-active", active);
            if (!icon) {
                return;
            }
            if (!active) {
                icon.textContent = "↕";
            } else if (state.sortDirection === "asc") {
                icon.textContent = "↑";
            } else {
                icon.textContent = "↓";
            }
        });
    }

    function sortNamespaces(rows) {
        var key = state.sortKey;
        var direction = state.sortDirection === "asc" ? 1 : -1;
        var sorted = rows.slice();
        if (!key) {
            return sorted;
        }
        sorted.sort(function (a, b) {
            var aNum = toNumber(a[key]);
            var bNum = toNumber(b[key]);
            if (aNum !== null && bNum !== null) {
                if (aNum === bNum) {
                    return String(a.namespace || "").localeCompare(String(b.namespace || ""));
                }
                return (aNum - bNum) * direction;
            }
            return String(a[key] || "").localeCompare(String(b[key] || "")) * direction;
        });
        return sorted;
    }

    function renderSummary(summary) {
        var cluster = summary && summary.cluster ? summary.cluster : {};
        if (totalCpuNode) {
            totalCpuNode.textContent = formatNumber(cluster.k8s_total_cpu, 0);
        }
        if (totalMemNode) {
            totalMemNode.textContent = formatNumber(cluster.k8s_total_mem, 0);
        }
        if (totalNodesNode) {
            totalNodesNode.textContent = formatNumber(cluster.node_number, 0);
        }
        if (totalNamespacesNode) {
            totalNamespacesNode.textContent = formatNumber(cluster.namespace_number, 0);
        }
        if (totalPodsNode) {
            totalPodsNode.textContent = formatNumber(cluster.pod_number, 0);
        }
        if (usedCpuTotalNode) {
            usedCpuTotalNode.textContent = formatNumber(summary.used_cpu_total, 2);
        }
        if (usedMemTotalNode) {
            usedMemTotalNode.textContent = formatNumber(summary.used_mem_total, 2);
        }
        if (updatedAtNode) {
            updatedAtNode.textContent = formatTextTime(summary.updated_at);
        }
    }

    function renderNamespaceTable() {
        if (!namespaceBody) {
            return;
        }
        var keyword = String((searchInput && searchInput.value) || "").trim().toLowerCase();
        var rows = state.namespaces.filter(function (item) {
            if (!keyword) {
                return true;
            }
            return String(item.namespace || "").toLowerCase().indexOf(keyword) >= 0;
        });
        rows = sortNamespaces(rows);

        if (namespaceCountNode) {
            namespaceCountNode.textContent = String(rows.length);
        }

        if (!rows.length) {
            namespaceBody.innerHTML = '<tr><td colspan="7"><div class="empty-inline empty-inline-v4">没有匹配的命名空间</div></td></tr>';
            return;
        }

        namespaceBody.innerHTML = rows
            .map(function (row) {
                var namespace = String(row.namespace || "");
                var isSelected = namespace && namespace === state.selectedNamespace;
                var cpu = toNumber(row.k8s_namespace_cpu_per);
                var mem = toNumber(row.k8s_namespace_mem_per);
                var rowClass = "k8smon-namespace-row-v2";
                if (isSelected) {
                    rowClass += " is-selected";
                }
                if ((cpu !== null && cpu >= 80) || (mem !== null && mem >= 80)) {
                    rowClass += " is-hot";
                }

                return (
                    '<tr class="' + rowClass + '" data-namespace="' + escapeHtml(namespace) + '">' +
                    "<td><code>" + escapeHtml(namespace || "--") + "</code></td>" +
                    "<td>" + formatNumber(row.k8s_namespace_cpu_num, 2) + "</td>" +
                    "<td>" + metricPill(row.k8s_namespace_cpu_per) + "</td>" +
                    "<td>" + formatNumber(row.k8s_namespace_mem_num, 2) + "</td>" +
                    "<td>" + metricPill(row.k8s_namespace_mem_per) + "</td>" +
                    "<td>" + formatNumber(row.namespace_pod, 0) + "</td>" +
                    "<td>" + escapeHtml(formatTextTime(row.create_time)) + "</td>" +
                    "</tr>"
                );
            })
            .join("");
    }

    function renderNodeTable() {
        if (!nodeBody) {
            return;
        }
        var rows = state.nodes.slice().sort(function (a, b) {
            var aMem = toNumber(a.node_used_mem_per) || 0;
            var bMem = toNumber(b.node_used_mem_per) || 0;
            return bMem - aMem;
        });

        if (nodeCountNode) {
            nodeCountNode.textContent = String(rows.length);
        }

        if (!rows.length) {
            nodeBody.innerHTML = '<tr><td colspan="8"><div class="empty-inline empty-inline-v4">暂无节点监控数据</div></td></tr>';
            return;
        }

        nodeBody.innerHTML = rows
            .map(function (row) {
                var nodeIp = String(row.node_ip || "");
                return (
                    '<tr class="k8smon-node-row-v2" data-node-ip="' + escapeHtml(nodeIp) + '">' +
                    "<td><code>" + escapeHtml(nodeIp || "--") + "</code></td>" +
                    "<td>" + formatNumber(row.k8s_total_nodecpu, 2) + "</td>" +
                    "<td>" + formatNumber(row.node_used_cpu_num, 2) + "</td>" +
                    "<td>" + metricPill(row.node_used_cpu_per) + "</td>" +
                    "<td>" + formatNumber(row.k8s_total_nodemem, 2) + "</td>" +
                    "<td>" + formatNumber(row.node_used_mem_num, 2) + "</td>" +
                    "<td>" + metricPill(row.node_used_mem_per) + "</td>" +
                    "<td>" + escapeHtml(formatTextTime(row.create_time)) + "</td>" +
                    "</tr>"
                );
            })
            .join("");
    }

    function hideTrendTooltip() {
        if (trendTooltipNode) {
            trendTooltipNode.hidden = true;
        }
        state.hoverIndex = -1;
        state.trendPreviewIndex = -1;
        state.trendPreviewX = -1;
    }

    function chartXForIndex(model, index) {
        if (model.labels.length <= 1) {
            return model.padding.left;
        }
        return model.padding.left + (index * model.plotW) / (model.labels.length - 1);
    }

    function hoverIndexByNearestX(model, x) {
        if (!model || !Array.isArray(model.labels) || !model.labels.length) {
            return -1;
        }
        if (model.labels.length === 1) {
            return 0;
        }
        var bestIndex = 0;
        var bestDistance = Number.POSITIVE_INFINITY;
        for (var idx = 0; idx < model.labels.length; idx += 1) {
            var pointX = chartXForIndex(model, idx);
            var distance = Math.abs(pointX - x);
            if (distance < bestDistance) {
                bestDistance = distance;
                bestIndex = idx;
            }
        }
        return bestIndex;
    }

    function canvasCoordsFromEvent(canvasNode, event, model) {
        var rect = canvasNode.getBoundingClientRect();
        var rawX = event.clientX - rect.left;
        var rawY = event.clientY - rect.top;
        var scaleX = rect.width > 0 && model && model.width ? model.width / rect.width : 1;
        var scaleY = rect.height > 0 && model && model.height ? model.height / rect.height : 1;
        return {
            x: rawX * scaleX,
            y: rawY * scaleY,
        };
    }

    function chartYForValue(model, value) {
        var num = toNumber(value);
        if (num === null) {
            return null;
        }
        var ratio = (num - model.yMin) / model.yRange;
        if (ratio < 0) {
            ratio = 0;
        } else if (ratio > 1) {
            ratio = 1;
        }
        return model.padding.top + model.plotH - ratio * model.plotH;
    }

    function drawTrend(trend) {
        if (!trendCanvas) {
            return;
        }
        var labels = Array.isArray(trend.timestamps) ? trend.timestamps : [];
        var cpuSeries = Array.isArray(trend.series && trend.series.cpu_per) ? trend.series.cpu_per : [];
        var memSeries = Array.isArray(trend.series && trend.series.mem_per) ? trend.series.mem_per : [];
        var podSeries = Array.isArray(trend.series && trend.series.pod) ? trend.series.pod : [];

        var hasData = labels.length && (cpuSeries.length || memSeries.length);
        if (trendEmptyNode) {
            trendEmptyNode.hidden = !!hasData;
        }
        if (!hasData) {
            var emptyCtx = trendCanvas.getContext("2d");
            if (emptyCtx) {
                emptyCtx.clearRect(0, 0, trendCanvas.width, trendCanvas.height);
            }
            state.chartModel = null;
            state.hoverIndex = -1;
            state.trendPreviewIndex = -1;
            state.trendPreviewX = -1;
            hideTrendTooltip();
            return;
        }

        var width = Math.max(trendCanvas.clientWidth || 360, 360);
        var height = 250;
        var dpr = window.devicePixelRatio || 1;
        trendCanvas.width = Math.round(width * dpr);
        trendCanvas.height = Math.round(height * dpr);
        trendCanvas.style.width = width + "px";
        trendCanvas.style.height = height + "px";

        var ctx = trendCanvas.getContext("2d");
        if (!ctx) {
            return;
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);

        var padding = { left: 42, right: 16, top: 16, bottom: 32 };
        var plotW = width - padding.left - padding.right;
        var plotH = height - padding.top - padding.bottom;
        var numericValues = cpuSeries.concat(memSeries).map(function (value) {
            return toNumber(value);
        }).filter(function (value) {
            return value !== null;
        });
        var minValue = 0;
        var maxValue = 100;
        if (numericValues.length) {
            var sortedValues = numericValues.slice().sort(function (a, b) {
                return a - b;
            });
            var lowSeries = sortedValues[0];
            var highSeries = sortedValues[sortedValues.length - 1];
            if (sortedValues.length >= 20) {
                var lowIndex = Math.floor((sortedValues.length - 1) * 0.03);
                var highIndex = Math.ceil((sortedValues.length - 1) * 0.97);
                lowSeries = sortedValues[Math.max(0, Math.min(lowIndex, sortedValues.length - 1))];
                highSeries = sortedValues[Math.max(0, Math.min(highIndex, sortedValues.length - 1))];
            }
            var rangeSeries = Math.max(highSeries - lowSeries, 0.08);
            var pad = Math.max(rangeSeries * 0.18, highSeries <= 2 ? 0.05 : 0.15);
            minValue = Math.max(0, lowSeries - pad);
            maxValue = highSeries + pad;
        }
        if (maxValue <= minValue) {
            maxValue = minValue + 0.1;
        }
        if (minValue < (maxValue - minValue) * 0.12) {
            minValue = 0;
        }
        var yRange = Math.max(maxValue - minValue, 0.08);

        var model = {
            labels: labels,
            cpuSeries: cpuSeries,
            memSeries: memSeries,
            podSeries: podSeries,
            width: width,
            height: height,
            padding: padding,
            plotW: plotW,
            plotH: plotH,
            yMin: minValue,
            yMax: maxValue,
            yRange: yRange,
        };
        state.chartModel = model;
        if (state.hoverIndex < 0 || state.hoverIndex >= labels.length) {
            state.hoverIndex = -1;
        }
        if (state.trendPreviewIndex >= labels.length) {
            state.trendPreviewIndex = -1;
        }
        if (state.trendPreviewX > model.width) {
            state.trendPreviewX = model.width;
        }

        function formatAxisValue(value) {
            if (model.yRange <= 1) {
                return value.toFixed(2);
            }
            if (model.yRange <= 4) {
                return value.toFixed(1);
            }
            return String(Math.round(value));
        }

        ctx.strokeStyle = "#d8e3f0";
        ctx.lineWidth = 1;
        for (var i = 0; i <= 4; i += 1) {
            var y = model.padding.top + (model.plotH * i) / 4;
            ctx.beginPath();
            ctx.moveTo(model.padding.left, y);
            ctx.lineTo(model.width - model.padding.right, y);
            ctx.stroke();
            ctx.fillStyle = "#7b90ab";
            ctx.font = "12px sans-serif";
            var yValue = model.yMax - (model.yRange * i) / 4;
            ctx.fillText(formatAxisValue(yValue), 8, y + 4);
        }

        function drawSeries(values, color) {
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.beginPath();
            var started = false;
            for (var idx = 0; idx < model.labels.length; idx += 1) {
                var y = chartYForValue(model, values[idx]);
                if (y === null) {
                    continue;
                }
                var x = chartXForIndex(model, idx);
                if (!started) {
                    ctx.moveTo(x, y);
                    started = true;
                } else {
                    ctx.lineTo(x, y);
                }
            }
            if (started) {
                ctx.stroke();
            }
        }

        drawSeries(model.cpuSeries, "#d97706");
        drawSeries(model.memSeries, "#dc2626");

        if (state.hoverIndex >= 0 && state.hoverIndex < model.labels.length) {
            var hoverX = chartXForIndex(model, state.hoverIndex);
            ctx.strokeStyle = "#9cb3cf";
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(hoverX, model.padding.top);
            ctx.lineTo(hoverX, model.height - model.padding.bottom);
            ctx.stroke();

            var cpuY = chartYForValue(model, model.cpuSeries[state.hoverIndex]);
            if (cpuY !== null) {
                ctx.fillStyle = "#d97706";
                ctx.beginPath();
                ctx.arc(hoverX, cpuY, 3.5, 0, Math.PI * 2);
                ctx.fill();
            }
            var memY = chartYForValue(model, model.memSeries[state.hoverIndex]);
            if (memY !== null) {
                ctx.fillStyle = "#dc2626";
                ctx.beginPath();
                ctx.arc(hoverX, memY, 3.5, 0, Math.PI * 2);
                ctx.fill();
            }
        }

        if (state.trendPreviewIndex >= 0 && state.trendPreviewX >= 0) {
            var previewLineX = state.trendPreviewX;
            var previewPointX = chartXForIndex(model, state.trendPreviewIndex);
            var previewCpuY = chartYForValue(model, model.cpuSeries[state.trendPreviewIndex]);
            var previewMemY = chartYForValue(model, model.memSeries[state.trendPreviewIndex]);
            ctx.save();
            ctx.strokeStyle = "rgba(31, 90, 166, 0.32)";
            ctx.lineWidth = 1;
            if (typeof ctx.setLineDash === "function") {
                ctx.setLineDash([4, 4]);
            }
            ctx.beginPath();
            ctx.moveTo(previewLineX, model.padding.top);
            ctx.lineTo(previewLineX, model.height - model.padding.bottom);
            ctx.stroke();
            ctx.restore();

            if (previewCpuY !== null) {
                ctx.strokeStyle = "#d97706";
                ctx.lineWidth = 2;
                ctx.fillStyle = "#ffffff";
                ctx.beginPath();
                ctx.arc(previewPointX, previewCpuY, 5, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
            }
            if (previewMemY !== null) {
                ctx.strokeStyle = "#dc2626";
                ctx.lineWidth = 2;
                ctx.fillStyle = "#ffffff";
                ctx.beginPath();
                ctx.arc(previewPointX, previewMemY, 5, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
            }
        }

        ctx.fillStyle = "#637a95";
        ctx.font = "12px sans-serif";
        var xLabelIndexes = [0, Math.floor((model.labels.length - 1) / 2), model.labels.length - 1];
        var printed = {};
        xLabelIndexes.forEach(function (idx) {
            if (idx < 0 || idx >= model.labels.length || printed[idx]) {
                return;
            }
            printed[idx] = true;
            var x = chartXForIndex(model, idx);
            var text = String(model.labels[idx] || "");
            var textWidth = ctx.measureText(text).width;
            ctx.fillText(text, Math.max(model.padding.left, Math.min(x - textWidth / 2, model.width - model.padding.right - textWidth)), model.height - 10);
        });
    }

    function renderTrend(trend, autoAnalyze) {
        state.trendData = trend;
        state.hoverIndex = -1;
        state.trendPreviewIndex = -1;
        state.trendPreviewX = -1;
        hideTrendTooltip();
        var namespace = String(trend.namespace || state.selectedNamespace || "");
        if (trendTitleNode) {
            trendTitleNode.textContent = namespace ? ("命名空间趋势 - " + namespace) : "命名空间趋势";
        }
        if (trendSubtitleNode) {
            trendSubtitleNode.textContent = "时间范围: 近 " + String(trend.hours || defaultTrendHours || 24) + " 小时";
        }
        drawTrend(trend);
        state.aiSignature = "";
        stopAutoAiAnalysis();
        resetAiStreaming("namespace");
        if (aiResultNode) {
            if (!aiStreamUrlTemplate) {
                setAiResult("AI分析接口未配置，请先设置 MONITORING_AI 配置。", false);
            } else if (!namespace) {
                setAiResult("请选择命名空间后自动分析。", false);
            } else if (autoAnalyze) {
                startAutoAiAnalysis(true);
            } else {
                setAiResult("趋势数据已更新，点击命名空间名称后自动开始分析。", false);
            }
        }
    }

    function showTrendTooltip(index, x, y) {
        if (!trendTooltipNode || !state.chartModel) {
            return;
        }
        var model = state.chartModel;
        if (index < 0 || index >= model.labels.length) {
            hideTrendTooltip();
            return;
        }
        var cpu = toNumber(model.cpuSeries[index]);
        var mem = toNumber(model.memSeries[index]);
        var pod = toNumber(model.podSeries[index]);
        var label = String(model.labels[index] || "--");

        trendTooltipNode.innerHTML =
            "<div><strong>" + escapeHtml(label) + "</strong></div>" +
            "<div>CPU%: " + (cpu === null ? "--" : cpu.toFixed(2) + "%") + "</div>" +
            "<div>MEM%: " + (mem === null ? "--" : mem.toFixed(2) + "%") + "</div>" +
            "<div>POD: " + (pod === null ? "--" : pod.toFixed(0)) + "</div>";
        trendTooltipNode.hidden = false;

        var wrapWidth = trendChartWrapNode ? trendChartWrapNode.clientWidth : model.width;
        var wrapHeight = trendChartWrapNode ? trendChartWrapNode.clientHeight : model.height;
        var canvasOffsetLeft = trendCanvas ? trendCanvas.offsetLeft : 0;
        var canvasOffsetTop = trendCanvas ? trendCanvas.offsetTop : 0;
        var tooltipWidth = trendTooltipNode.offsetWidth || 160;
        var tooltipHeight = trendTooltipNode.offsetHeight || 86;
        var left = canvasOffsetLeft + x + 12;
        var top = canvasOffsetTop + y + 12;

        if (left + tooltipWidth > wrapWidth - 8) {
            left = canvasOffsetLeft + x - tooltipWidth - 12;
        }
        if (top + tooltipHeight > wrapHeight - 8) {
            top = canvasOffsetTop + y - tooltipHeight - 12;
        }
        if (left < 8) {
            left = 8;
        }
        if (top < 8) {
            top = 8;
        }
        trendTooltipNode.style.left = left + "px";
        trendTooltipNode.style.top = top + "px";
    }

    function showTrendTooltipForIndex(index, xOverride) {
        var model = state.chartModel;
        if (!model || index < 0 || index >= model.labels.length) {
            hideTrendTooltip();
            return;
        }
        var x = typeof xOverride === "number" ? xOverride : chartXForIndex(model, index);
        var cpuY = chartYForValue(model, model.cpuSeries[index]);
        var memY = chartYForValue(model, model.memSeries[index]);
        var podY = chartYForValue(model, model.podSeries[index]);
        var anchorY = model.padding.top + 24;
        var tops = [cpuY, memY, podY].filter(function (value) {
            return typeof value === "number";
        });
        if (tops.length) {
            anchorY = Math.max(model.padding.top + 12, Math.min.apply(null, tops) - 18);
        }
        showTrendTooltip(index, x, anchorY);
    }

    function setTrendPreview(index, previewX, redraw) {
        var model = state.chartModel;
        if (!model || !Array.isArray(model.labels) || !model.labels.length) {
            state.trendPreviewIndex = -1;
            state.trendPreviewX = -1;
            hideTrendTooltip();
            return;
        }
        var nextIndex = Number(index);
        var nextPreviewX = Number(previewX);
        if (!Number.isFinite(nextIndex)) {
            nextIndex = -1;
        } else {
            nextIndex = Math.max(0, Math.min(Math.round(nextIndex), model.labels.length - 1));
        }
        if (!Number.isFinite(nextPreviewX)) {
            nextPreviewX = -1;
        } else {
            nextPreviewX = Math.max(0, Math.min(nextPreviewX, model.width));
        }
        var changed = nextIndex !== state.trendPreviewIndex || nextPreviewX !== state.trendPreviewX;
        state.trendPreviewIndex = nextIndex;
        state.trendPreviewX = nextPreviewX;
        if (nextIndex < 0) {
            state.hoverIndex = -1;
        } else {
            state.hoverIndex = nextIndex;
        }
        if (redraw && changed && state.trendData) {
            drawTrend(state.trendData);
        }
        if (nextIndex >= 0) {
            showTrendTooltipForIndex(nextIndex, nextPreviewX >= 0 ? nextPreviewX : undefined);
        } else {
            hideTrendTooltip();
        }
    }

    function setTrendSelection(index, redraw) {
        var model = state.chartModel;
        if (!model || !Array.isArray(model.labels) || !model.labels.length) {
            state.hoverIndex = -1;
            state.trendPreviewIndex = -1;
            state.trendPreviewX = -1;
            hideTrendTooltip();
            return;
        }
        var nextIndex = Number(index);
        if (!Number.isFinite(nextIndex)) {
            nextIndex = model.labels.length - 1;
        }
        nextIndex = Math.max(0, Math.min(Math.round(nextIndex), model.labels.length - 1));
        var changed = nextIndex !== state.hoverIndex;
        state.hoverIndex = nextIndex;
        state.trendPreviewIndex = -1;
        state.trendPreviewX = -1;
        if (redraw && changed && state.trendData) {
            drawTrend(state.trendData);
        }
        showTrendTooltipForIndex(nextIndex);
    }

    function hideNodeTrendTooltip() {
        if (nodeTrendTooltipNode) {
            nodeTrendTooltipNode.hidden = true;
        }
        state.nodeTrendHoverIndex = -1;
        state.nodeTrendPreviewIndex = -1;
        state.nodeTrendPreviewX = -1;
    }

    function buildNodeTrendUrl(nodeIp) {
        var target = nodeTrendUrlTemplate.replace("__NODE__", encodeURIComponent(nodeIp));
        return new URL(target, window.location.origin);
    }

    function showNodeTrendTooltipForIndex(index, xOverride) {
        var model = state.nodeTrendChartModel;
        if (!model || index < 0 || index >= model.labels.length) {
            hideNodeTrendTooltip();
            return;
        }
        var x = typeof xOverride === "number" ? xOverride : chartXForIndex(model, index);
        var cpuY = chartYForValue(model, model.cpuPerSeries[index]);
        var memY = chartYForValue(model, model.memPerSeries[index]);
        var anchorY = model.padding.top + 28;
        if (cpuY !== null && memY !== null) {
            anchorY = Math.max(model.padding.top + 16, Math.min(cpuY, memY) - 18);
        } else if (cpuY !== null) {
            anchorY = Math.max(model.padding.top + 16, cpuY - 18);
        } else if (memY !== null) {
            anchorY = Math.max(model.padding.top + 16, memY - 18);
        }
        showNodeTrendTooltip(index, x, anchorY);
    }

    function setNodeTrendPreview(index, previewX, redraw) {
        var model = state.nodeTrendChartModel;
        if (!model || !Array.isArray(model.labels) || !model.labels.length) {
            state.nodeTrendPreviewIndex = -1;
            state.nodeTrendPreviewX = -1;
            hideNodeTrendTooltip();
            return;
        }
        var nextIndex = Number(index);
        var nextPreviewX = Number(previewX);
        if (!Number.isFinite(nextIndex)) {
            nextIndex = -1;
        } else {
            nextIndex = Math.max(0, Math.min(Math.round(nextIndex), model.labels.length - 1));
        }
        if (!Number.isFinite(nextPreviewX)) {
            nextPreviewX = -1;
        } else {
            nextPreviewX = Math.max(0, Math.min(nextPreviewX, model.width));
        }
        var changed = nextIndex !== state.nodeTrendPreviewIndex || nextPreviewX !== state.nodeTrendPreviewX;
        state.nodeTrendPreviewIndex = nextIndex;
        state.nodeTrendPreviewX = nextPreviewX;
        if (nextIndex < 0) {
            state.nodeTrendHoverIndex = -1;
        } else {
            state.nodeTrendHoverIndex = nextIndex;
        }
        if (redraw && changed && state.nodeTrendData) {
            drawNodeTrend(state.nodeTrendData);
        }
        if (nextIndex >= 0) {
            showNodeTrendTooltipForIndex(nextIndex, nextPreviewX >= 0 ? nextPreviewX : undefined);
        } else {
            hideNodeTrendTooltip();
        }
    }

    function setNodeTrendSelection(index, redraw) {
        var model = state.nodeTrendChartModel;
        if (!model || !Array.isArray(model.labels) || !model.labels.length) {
            state.nodeTrendHoverIndex = -1;
            state.nodeTrendPreviewIndex = -1;
            state.nodeTrendPreviewX = -1;
            hideNodeTrendTooltip();
            return;
        }
        var nextIndex = Number(index);
        if (!Number.isFinite(nextIndex)) {
            nextIndex = model.labels.length - 1;
        }
        nextIndex = Math.max(0, Math.min(Math.round(nextIndex), model.labels.length - 1));
        var changed = nextIndex !== state.nodeTrendHoverIndex;
        state.nodeTrendHoverIndex = nextIndex;
        state.nodeTrendPreviewIndex = -1;
        state.nodeTrendPreviewX = -1;
        if (redraw && changed && state.nodeTrendData) {
            drawNodeTrend(state.nodeTrendData);
        }
        showNodeTrendTooltipForIndex(nextIndex);
    }

    function drawNodeTrend(trend) {
        if (!nodeTrendCanvas) {
            return;
        }
        var labels = Array.isArray(trend.timestamps) ? trend.timestamps : [];
        var cpuPerSeries = Array.isArray(trend.series && trend.series.cpu_per) ? trend.series.cpu_per : [];
        var memPerSeries = Array.isArray(trend.series && trend.series.mem_per) ? trend.series.mem_per : [];
        var cpuNumSeries = Array.isArray(trend.series && trend.series.cpu_num) ? trend.series.cpu_num : [];
        var memNumSeries = Array.isArray(trend.series && trend.series.mem_num) ? trend.series.mem_num : [];

        var hasData = labels.length && (cpuPerSeries.length || memPerSeries.length);
        if (nodeTrendEmptyNode) {
            nodeTrendEmptyNode.hidden = !!hasData;
        }
        if (!hasData) {
            var emptyCtx = nodeTrendCanvas.getContext("2d");
            if (emptyCtx) {
                emptyCtx.clearRect(0, 0, nodeTrendCanvas.width, nodeTrendCanvas.height);
            }
            state.nodeTrendChartModel = null;
            state.nodeTrendHoverIndex = -1;
            state.nodeTrendPreviewIndex = -1;
            state.nodeTrendPreviewX = -1;
            hideNodeTrendTooltip();
            return;
        }

        var width = Math.max(nodeTrendCanvas.clientWidth || 520, 520);
        var height = 320;
        var dpr = window.devicePixelRatio || 1;
        nodeTrendCanvas.width = Math.round(width * dpr);
        nodeTrendCanvas.height = Math.round(height * dpr);
        nodeTrendCanvas.style.width = width + "px";
        nodeTrendCanvas.style.height = height + "px";

        var ctx = nodeTrendCanvas.getContext("2d");
        if (!ctx) {
            return;
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);

        var padding = { left: 46, right: 16, top: 16, bottom: 58 };
        var plotW = width - padding.left - padding.right;
        var plotH = height - padding.top - padding.bottom;
        var numericValues = cpuPerSeries.concat(memPerSeries).map(function (value) {
            return toNumber(value);
        }).filter(function (value) {
            return value !== null;
        });
        var minValue = 0;
        var maxValue = 100;
        if (numericValues.length) {
            var sortedValues = numericValues.slice().sort(function (a, b) {
                return a - b;
            });
            var lowSeries = sortedValues[0];
            var highSeries = sortedValues[sortedValues.length - 1];
            if (sortedValues.length >= 20) {
                var lowIndex = Math.floor((sortedValues.length - 1) * 0.03);
                var highIndex = Math.ceil((sortedValues.length - 1) * 0.97);
                lowSeries = sortedValues[Math.max(0, Math.min(lowIndex, sortedValues.length - 1))];
                highSeries = sortedValues[Math.max(0, Math.min(highIndex, sortedValues.length - 1))];
            }
            var rangeSeries = Math.max(highSeries - lowSeries, 0.08);
            var pad = Math.max(rangeSeries * 0.18, highSeries <= 2 ? 0.05 : 0.15);
            minValue = Math.max(0, lowSeries - pad);
            maxValue = highSeries + pad;
        }
        if (maxValue <= minValue) {
            maxValue = minValue + 0.1;
        }
        if (minValue < (maxValue - minValue) * 0.12) {
            minValue = 0;
        }
        var yRange = Math.max(maxValue - minValue, 0.08);

        var model = {
            labels: labels,
            cpuPerSeries: cpuPerSeries,
            memPerSeries: memPerSeries,
            cpuNumSeries: cpuNumSeries,
            memNumSeries: memNumSeries,
            width: width,
            height: height,
            padding: padding,
            plotW: plotW,
            plotH: plotH,
            yMin: minValue,
            yMax: maxValue,
            yRange: yRange,
        };
        state.nodeTrendChartModel = model;
        if (state.nodeTrendHoverIndex < 0 || state.nodeTrendHoverIndex >= labels.length) {
            state.nodeTrendHoverIndex = -1;
        }
        if (state.nodeTrendPreviewIndex >= labels.length) {
            state.nodeTrendPreviewIndex = -1;
        }
        if (state.nodeTrendPreviewX > model.width) {
            state.nodeTrendPreviewX = model.width;
        }

        function formatAxisValue(value) {
            if (model.yRange <= 1) {
                return value.toFixed(2);
            }
            if (model.yRange <= 4) {
                return value.toFixed(1);
            }
            return String(Math.round(value));
        }

        ctx.strokeStyle = "#d8e3f0";
        ctx.lineWidth = 1;
        for (var i = 0; i <= 4; i += 1) {
            var y = model.padding.top + (model.plotH * i) / 4;
            ctx.beginPath();
            ctx.moveTo(model.padding.left, y);
            ctx.lineTo(model.width - model.padding.right, y);
            ctx.stroke();
            ctx.fillStyle = "#7b90ab";
            ctx.font = "12px sans-serif";
            var yValue = model.yMax - (model.yRange * i) / 4;
            ctx.fillText(formatAxisValue(yValue), 8, y + 4);
        }

        function drawSeries(values, color) {
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.beginPath();
            var started = false;
            for (var idx = 0; idx < model.labels.length; idx += 1) {
                var y = chartYForValue(model, values[idx]);
                if (y === null) {
                    continue;
                }
                var x = chartXForIndex(model, idx);
                if (!started) {
                    ctx.moveTo(x, y);
                    started = true;
                } else {
                    ctx.lineTo(x, y);
                }
            }
            if (started) {
                ctx.stroke();
            }
        }

        drawSeries(model.cpuPerSeries, "#d97706");
        drawSeries(model.memPerSeries, "#dc2626");

        if (state.nodeTrendHoverIndex >= 0 && state.nodeTrendHoverIndex < model.labels.length) {
            var selectedX = chartXForIndex(model, state.nodeTrendHoverIndex);
            var leftBound = state.nodeTrendHoverIndex === 0
                ? model.padding.left
                : (chartXForIndex(model, state.nodeTrendHoverIndex - 1) + selectedX) / 2;
            var rightBound = state.nodeTrendHoverIndex === model.labels.length - 1
                ? model.width - model.padding.right
                : (selectedX + chartXForIndex(model, state.nodeTrendHoverIndex + 1)) / 2;
            ctx.fillStyle = "rgba(50, 105, 179, 0.08)";
            ctx.fillRect(leftBound, model.padding.top, Math.max(2, rightBound - leftBound), model.plotH);
            ctx.strokeStyle = "#9cb3cf";
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(selectedX, model.padding.top);
            ctx.lineTo(selectedX, model.height - model.padding.bottom);
            ctx.stroke();

            var cpuY = chartYForValue(model, model.cpuPerSeries[state.nodeTrendHoverIndex]);
            if (cpuY !== null) {
                ctx.fillStyle = "#d97706";
                ctx.beginPath();
                ctx.arc(selectedX, cpuY, 5, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = "#fff7ed";
                ctx.beginPath();
                ctx.arc(selectedX, cpuY, 2.2, 0, Math.PI * 2);
                ctx.fill();
            }
            var memY = chartYForValue(model, model.memPerSeries[state.nodeTrendHoverIndex]);
            if (memY !== null) {
                ctx.fillStyle = "#dc2626";
                ctx.beginPath();
                ctx.arc(selectedX, memY, 5, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = "#fef2f2";
                ctx.beginPath();
                ctx.arc(selectedX, memY, 2.2, 0, Math.PI * 2);
                ctx.fill();
            }
        }

        if (state.nodeTrendPreviewIndex >= 0 && state.nodeTrendPreviewX >= 0) {
            var previewLineX = state.nodeTrendPreviewX;
            ctx.save();
            ctx.strokeStyle = "rgba(31, 90, 166, 0.32)";
            ctx.lineWidth = 1;
            if (typeof ctx.setLineDash === "function") {
                ctx.setLineDash([4, 4]);
            }
            ctx.beginPath();
            ctx.moveTo(previewLineX, model.padding.top);
            ctx.lineTo(previewLineX, model.height - model.padding.bottom);
            ctx.stroke();
            ctx.restore();

            var previewPointX = chartXForIndex(model, state.nodeTrendPreviewIndex);
            var previewCpuY = chartYForValue(model, model.cpuPerSeries[state.nodeTrendPreviewIndex]);
            var previewMemY = chartYForValue(model, model.memPerSeries[state.nodeTrendPreviewIndex]);
            if (previewCpuY !== null) {
                ctx.strokeStyle = "#d97706";
                ctx.lineWidth = 2;
                ctx.fillStyle = "#ffffff";
                ctx.beginPath();
                ctx.arc(previewPointX, previewCpuY, 5.5, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
            }
            if (previewMemY !== null) {
                ctx.strokeStyle = "#dc2626";
                ctx.lineWidth = 2;
                ctx.fillStyle = "#ffffff";
                ctx.beginPath();
                ctx.arc(previewPointX, previewMemY, 5.5, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
            }
        }

        ctx.fillStyle = "#637a95";
        ctx.font = "12px sans-serif";
        var xLabelIndexes = [0, Math.floor((model.labels.length - 1) / 2), model.labels.length - 1];
        var printed = {};
        xLabelIndexes.forEach(function (idx) {
            if (idx < 0 || idx >= model.labels.length || printed[idx]) {
                return;
            }
            printed[idx] = true;
            var x = chartXForIndex(model, idx);
            var text = String(model.labels[idx] || "");
            var textWidth = ctx.measureText(text).width;
            ctx.fillText(text, Math.max(model.padding.left, Math.min(x - textWidth / 2, model.width - model.padding.right - textWidth)), model.height - 6);
        });
    }

    function renderNodeTrend(trend, autoAnalyze) {
        state.nodeTrendData = trend;
        state.nodeTrendHoverIndex = -1;
        state.nodeTrendPreviewIndex = -1;
        state.nodeTrendPreviewX = -1;
        hideNodeTrendTooltip();
        var nodeIp = String(trend.node_ip || state.selectedNodeIp || "");
        if (nodeModalTitleNode) {
            nodeModalTitleNode.textContent = nodeIp ? ("节点趋势 - " + nodeIp) : "节点趋势";
        }
        if (nodeModalSubtitleNode) {
            nodeModalSubtitleNode.textContent = "时间范围: 近 " + String(trend.hours || defaultTrendHours || 24) + " 小时";
        }
        drawNodeTrend(trend);
        state.nodeAiSignature = "";
        stopNodeAutoAiAnalysis();
        resetAiStreaming("node");
        if (nodeAiResultNode) {
            var hasPoints = Array.isArray(trend.timestamps) && trend.timestamps.length > 0;
            if (!nodeAiStreamUrlTemplate) {
                setNodeAiResult("AI分析接口未配置，请先设置 MONITORING_AI 配置。", false);
            } else if (!hasPoints) {
                setNodeAiResult("当前节点在所选时间范围无趋势数据，无法进行 AI 分析。", false);
            } else if (!nodeIp) {
                setNodeAiResult("请选择节点后自动分析。", false);
            } else if (autoAnalyze) {
                startNodeAutoAiAnalysis(true);
            } else {
                setNodeAiResult("节点趋势已更新，将自动开始分析。", false);
            }
        }
    }

    function showNodeTrendTooltip(index, x, y) {
        if (!nodeTrendTooltipNode || !state.nodeTrendChartModel) {
            return;
        }
        var model = state.nodeTrendChartModel;
        if (index < 0 || index >= model.labels.length) {
            hideNodeTrendTooltip();
            return;
        }
        var cpuPer = toNumber(model.cpuPerSeries[index]);
        var memPer = toNumber(model.memPerSeries[index]);
        var cpuNum = toNumber(model.cpuNumSeries[index]);
        var memNum = toNumber(model.memNumSeries[index]);
        var label = String(model.labels[index] || "--");
        nodeTrendTooltipNode.innerHTML =
            "<div><strong>" + escapeHtml(label) + "</strong></div>" +
            "<div>CPU已用: " + (cpuNum === null ? "--" : cpuNum.toFixed(2) + " 核") + "</div>" +
            "<div>CPU%: " + (cpuPer === null ? "--" : cpuPer.toFixed(2) + "%") + "</div>" +
            "<div>内存已用: " + (memNum === null ? "--" : memNum.toFixed(2) + " GB") + "</div>" +
            "<div>内存%: " + (memPer === null ? "--" : memPer.toFixed(2) + "%") + "</div>";
        nodeTrendTooltipNode.hidden = false;

        var wrapWidth = nodeTrendChartWrapNode ? nodeTrendChartWrapNode.clientWidth : model.width;
        var wrapHeight = nodeTrendChartWrapNode ? nodeTrendChartWrapNode.clientHeight : model.height;
        var canvasOffsetLeft = nodeTrendCanvas ? nodeTrendCanvas.offsetLeft : 0;
        var canvasOffsetTop = nodeTrendCanvas ? nodeTrendCanvas.offsetTop : 0;
        var tooltipWidth = nodeTrendTooltipNode.offsetWidth || 170;
        var tooltipHeight = nodeTrendTooltipNode.offsetHeight || 102;
        var left = canvasOffsetLeft + x + 12;
        var top = canvasOffsetTop + y + 12;
        if (left + tooltipWidth > wrapWidth - 8) {
            left = canvasOffsetLeft + x - tooltipWidth - 12;
        }
        if (top + tooltipHeight > wrapHeight - 8) {
            top = canvasOffsetTop + y - tooltipHeight - 12;
        }
        if (left < 8) {
            left = 8;
        }
        if (top < 8) {
            top = 8;
        }
        nodeTrendTooltipNode.style.left = left + "px";
        nodeTrendTooltipNode.style.top = top + "px";
    }

    function openNodeModal(nodeIp) {
        if (!nodeModal || !nodeIp) {
            return;
        }
        state.nodeModalOpen = true;
        state.selectedNodeIp = String(nodeIp || "");
        state.nodeAiSignature = "";
        stopNodeAutoAiAnalysis();
        nodeModal.hidden = false;
        document.body.classList.add("modal-open");
        if (nodeModalTitleNode) {
            nodeModalTitleNode.textContent = "节点趋势 - " + state.selectedNodeIp;
        }
        if (nodeModalSubtitleNode) {
            nodeModalSubtitleNode.textContent = "正在加载节点趋势数据...";
        }
        if (nodeTrendHoursInput && !nodeTrendHoursInput.value) {
            nodeTrendHoursInput.value = String(defaultTrendHours || 24);
        }
        if (nodeAiResultNode) {
            if (!nodeAiStreamUrlTemplate) {
                setNodeAiResult("AI分析接口未配置，请先设置 MONITORING_AI 配置。", false);
            } else {
                setNodeAiResult("节点趋势加载后，将自动开始分析。", false);
            }
        }
        if (!nodeTrendUrlTemplate) {
            if (nodeModalSubtitleNode) {
                nodeModalSubtitleNode.textContent = "节点趋势接口未配置";
            }
            if (nodeAiResultNode) {
                setNodeAiResult("节点趋势接口未配置，无法进行 AI 分析。", false);
            }
            return;
        }
        loadNodeTrend(state.selectedNodeIp, false, true);
    }

    function closeNodeModal() {
        if (!nodeModal) {
            return;
        }
        state.nodeModalOpen = false;
        nodeModal.hidden = true;
        document.body.classList.remove("modal-open");
        state.nodeTrendHoverIndex = -1;
        state.nodeTrendPreviewIndex = -1;
        hideNodeTrendTooltip();
        stopNodeAutoAiAnalysis();
        if (nodeAiResultNode) {
            nodeAiResultNode.classList.remove("is-loading");
        }
    }

    function loadNodeTrend(nodeIp, silent, autoAnalyze) {
        if (!nodeIp || !nodeTrendUrlTemplate) {
            return Promise.resolve();
        }
        var hours = Number(nodeTrendHoursInput && nodeTrendHoursInput.value ? nodeTrendHoursInput.value : defaultTrendHours || 24);
        var url = buildNodeTrendUrl(nodeIp);
        url.searchParams.set("hours", String(hours));
        return requestJson(url.pathname + url.search)
            .then(function (payload) {
                renderNodeTrend(payload.trend || {}, !!autoAnalyze);
            })
            .catch(function (error) {
                if (!silent) {
                    setNotice("warning", error.message || "节点趋势加载失败");
                }
                renderNodeTrend({
                    node_ip: nodeIp,
                    hours: hours,
                    timestamps: [],
                    series: { cpu_num: [], cpu_per: [], mem_num: [], mem_per: [] },
                    last_point: {},
                }, false);
            });
    }

    function setAiResult(text, loading, normalize) {
        if (!aiResultNode) {
            return;
        }
        aiResultNode.textContent = normalize === false ? String(text || "") : normalizeAiText(text);
        aiResultNode.classList.toggle("is-loading", !!loading);
    }

    function setNodeAiResult(text, loading, normalize) {
        if (!nodeAiResultNode) {
            return;
        }
        nodeAiResultNode.textContent = normalize === false ? String(text || "") : normalizeAiText(text);
        nodeAiResultNode.classList.toggle("is-loading", !!loading);
    }

    function clearAiTyping(kind) {
        var timerKey = kind === "node" ? "nodeAiTypingTimer" : "aiTypingTimer";
        if (state[timerKey]) {
            window.clearInterval(state[timerKey]);
            state[timerKey] = null;
        }
    }

    function resetAiStreaming(kind) {
        if (kind === "node") {
            clearAiTyping("node");
            state.nodeAiStreamText = "";
            state.nodeAiPendingText = "";
            state.nodeAiFinalizeText = null;
            return;
        }
        clearAiTyping("namespace");
        state.aiStreamText = "";
        state.aiPendingText = "";
        state.aiFinalizeText = null;
    }

    function finalizeAiStreaming(kind, finalText) {
        if (kind === "node") {
            state.nodeAiFinalizeText = String(finalText || "");
            if (!state.nodeAiTypingTimer && !state.nodeAiPendingText) {
                state.nodeAiStreamText = state.nodeAiFinalizeText;
                setNodeAiResult(state.nodeAiFinalizeText, false, true);
                state.nodeAiFinalizeText = null;
            }
            return;
        }
        state.aiFinalizeText = String(finalText || "");
        if (!state.aiTypingTimer && !state.aiPendingText) {
            state.aiStreamText = state.aiFinalizeText;
            setAiResult(state.aiFinalizeText, false, true);
            state.aiFinalizeText = null;
        }
    }

    function enqueueAiChunk(kind, chunk) {
        var text = String(chunk || "");
        if (!text) {
            return;
        }

        var isNode = kind === "node";
        var pendingKey = isNode ? "nodeAiPendingText" : "aiPendingText";
        var streamKey = isNode ? "nodeAiStreamText" : "aiStreamText";
        var timerKey = isNode ? "nodeAiTypingTimer" : "aiTypingTimer";

        state[pendingKey] += text;

        if (state[timerKey]) {
            return;
        }

        state[timerKey] = window.setInterval(function () {
            var pending = String(state[pendingKey] || "");
            if (!pending) {
                clearAiTyping(kind);
                if (isNode && state.nodeAiFinalizeText !== null) {
                    state.nodeAiStreamText = state.nodeAiFinalizeText;
                    setNodeAiResult(state.nodeAiFinalizeText, false, true);
                    state.nodeAiFinalizeText = null;
                } else if (!isNode && state.aiFinalizeText !== null) {
                    state.aiStreamText = state.aiFinalizeText;
                    setAiResult(state.aiFinalizeText, false, true);
                    state.aiFinalizeText = null;
                }
                return;
            }

            var step = pending.length > 24 ? 8 : pending.length > 8 ? 4 : 1;
            var piece = pending.slice(0, step);
            state[pendingKey] = pending.slice(piece.length);
            state[streamKey] += piece;

            if (isNode) {
                setNodeAiResult(state[streamKey], true, false);
            } else {
                setAiResult(state[streamKey], true, false);
            }
        }, 20);
    }

    function normalizeAiText(value) {
        var text = String(value || "");
        text = text.replace(/\r\n/g, "\n");
        text = text.replace(/^#{1,6}\s*/gm, "");
        text = text.replace(/\*\*(.*?)\*\*/g, "$1");
        text = text.replace(/^\s*[*-]\s+/gm, "- ");
        text = text.replace(/`{1,3}/g, "");
        text = text.replace(/\n{3,}/g, "\n\n");
        text = text.replace(/\n+/g, " ");
        text = text.replace(/\s+/g, " ").trim();
        return text;
        if (text.length <= aiResultMaxChars) {
            return text;
        }
        var shortText = text.slice(0, aiResultMaxChars).replace(/[，,；;。 ]+$/, "");
        return shortText + "。";
    }

    function buildAiStreamUrl(namespace) {
        var target = aiStreamUrlTemplate.replace("__NAMESPACE__", encodeURIComponent(namespace));
        return new URL(target, window.location.origin);
    }

    function buildNodeAiStreamUrl(nodeIp) {
        var target = nodeAiStreamUrlTemplate.replace("__NODE__", encodeURIComponent(nodeIp));
        return new URL(target, window.location.origin);
    }

    function appendRequestNonce(url) {
        if (!url || !url.searchParams) {
            return url;
        }
        url.searchParams.set("_ts", String(Date.now()));
        url.searchParams.set("_rid", Math.random().toString(36).slice(2, 10));
        return url;
    }

    function stopAutoAiAnalysis() {
        if (state.aiAbortController) {
            state.aiAbortController.abort();
        }
        state.aiAbortController = null;
        state.aiBusy = false;
        clearAiTyping("namespace");
    }

    function stopNodeAutoAiAnalysis() {
        if (state.nodeAiAbortController) {
            state.nodeAiAbortController.abort();
        }
        state.nodeAiAbortController = null;
        state.nodeAiBusy = false;
        clearAiTyping("node");
    }

    function streamResponseText(response, onChunk) {
        if (!response.body || typeof response.body.getReader !== "function") {
            return response.text().then(function (text) {
                if (text) {
                    onChunk(text);
                }
            });
        }
        var reader = response.body.getReader();
        var decoder = new TextDecoder("utf-8");

        function readNext() {
            return reader.read().then(function (result) {
                if (result.done) {
                    var remain = decoder.decode();
                    if (remain) {
                        onChunk(remain);
                    }
                    return;
                }
                var text = decoder.decode(result.value, { stream: true });
                if (text) {
                    onChunk(text);
                }
                return readNext();
            });
        }

        return readNext();
    }

    function startAutoAiAnalysis(force) {
        if (!aiResultNode) {
            return;
        }
        if (!aiStreamUrlTemplate) {
            setAiResult("AI分析接口未配置，请先设置 MONITORING_AI 配置。", false);
            return;
        }
        if (!state.selectedNamespace) {
            setAiResult("请选择命名空间后自动分析。", false);
            return;
        }
        var hours = Number(trendHoursInput && trendHoursInput.value ? trendHoursInput.value : defaultTrendHours || 24);
        var signature = state.selectedNamespace + "|" + String(hours);
        if (!force && signature === state.aiSignature) {
            return;
        }

        state.aiSignature = signature;
        stopAutoAiAnalysis();
        state.aiBusy = true;
        resetAiStreaming("namespace");

        var controller = new AbortController();
        state.aiAbortController = controller;
        setAiResult("AI 正在基于当前命名空间与时间范围进行分析...", true, false);

        var streamUrl = appendRequestNonce(buildAiStreamUrl(state.selectedNamespace));
        streamUrl.searchParams.set("hours", String(hours));

        var output = "";
        fetch(streamUrl.pathname + streamUrl.search, {
            method: "GET",
            credentials: "same-origin",
            cache: "no-store",
            signal: controller.signal,
            headers: {
                "Accept": "text/plain",
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
            },
        })
            .then(function (response) {
                if (!response.ok) {
                    return response.text().then(function (text) {
                        throw new Error(text || ("AI分析失败（HTTP " + response.status + "）"));
                    });
                }
                return streamResponseText(response, function (chunk) {
                    if (controller.signal.aborted) {
                        return;
                    }
                    output += chunk;
                    enqueueAiChunk("namespace", chunk);
                });
            })
            .then(function () {
                if (controller.signal.aborted) {
                    return;
                }
                finalizeAiStreaming("namespace", output || "分析结果为空");
            })
            .catch(function (error) {
                if (error && error.name === "AbortError") {
                    return;
                }
                state.aiSignature = "";
                resetAiStreaming("namespace");
                setAiResult("分析失败: " + (error.message || "未知错误"), false, true);
            })
            .finally(function () {
                if (state.aiAbortController === controller) {
                    state.aiAbortController = null;
                    state.aiBusy = false;
                }
            });
    }

    function startNodeAutoAiAnalysis(force) {
        if (!nodeAiResultNode) {
            return;
        }
        if (!state.nodeModalOpen || !state.selectedNodeIp) {
            return;
        }
        if (!nodeAiStreamUrlTemplate) {
            setNodeAiResult("AI分析接口未配置，请先设置 MONITORING_AI 配置。", false);
            return;
        }
        var trend = state.nodeTrendData || {};
        var timestamps = Array.isArray(trend.timestamps) ? trend.timestamps : [];
        if (!timestamps.length) {
            setNodeAiResult("当前节点在所选时间范围无趋势数据，无法进行 AI 分析。", false);
            state.nodeAiSignature = "";
            stopNodeAutoAiAnalysis();
            return;
        }
        var hours = Number(nodeTrendHoursInput && nodeTrendHoursInput.value ? nodeTrendHoursInput.value : defaultTrendHours || 24);
        var signature = state.selectedNodeIp + "|" + String(hours);
        if (!force && signature === state.nodeAiSignature) {
            return;
        }

        state.nodeAiSignature = signature;
        stopNodeAutoAiAnalysis();
        state.nodeAiBusy = true;
        resetAiStreaming("node");

        var controller = new AbortController();
        state.nodeAiAbortController = controller;
        setNodeAiResult("AI 正在基于当前节点与时间范围分析 CPU 和内存资源使用情况...", true, false);

        var streamUrl = appendRequestNonce(buildNodeAiStreamUrl(state.selectedNodeIp));
        streamUrl.searchParams.set("hours", String(hours));

        var output = "";
        fetch(streamUrl.pathname + streamUrl.search, {
            method: "GET",
            credentials: "same-origin",
            cache: "no-store",
            signal: controller.signal,
            headers: {
                "Accept": "text/plain",
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
            },
        })
            .then(function (response) {
                if (!response.ok) {
                    return response.text().then(function (text) {
                        throw new Error(text || ("AI分析失败（HTTP " + response.status + "）"));
                    });
                }
                return streamResponseText(response, function (chunk) {
                    if (controller.signal.aborted) {
                        return;
                    }
                    output += chunk;
                    enqueueAiChunk("node", chunk);
                });
            })
            .then(function () {
                if (controller.signal.aborted) {
                    return;
                }
                finalizeAiStreaming("node", output || "分析结果为空");
            })
            .catch(function (error) {
                if (error && error.name === "AbortError") {
                    return;
                }
                state.nodeAiSignature = "";
                resetAiStreaming("node");
                setNodeAiResult("分析失败: " + (error.message || "未知错误"), false, true);
            })
            .finally(function () {
                if (state.nodeAiAbortController === controller) {
                    state.nodeAiAbortController = null;
                    state.nodeAiBusy = false;
                }
            });
    }

    function buildTrendUrl(namespace) {
        var target = trendUrlTemplate.replace("__NAMESPACE__", encodeURIComponent(namespace));
        return new URL(target, window.location.origin);
    }

    function loadTrend(namespace, silent, autoAnalyze) {
        if (!namespace) {
            return Promise.resolve();
        }
        var hours = Number(trendHoursInput && trendHoursInput.value ? trendHoursInput.value : defaultTrendHours || 24);
        var url = buildTrendUrl(namespace);
        url.searchParams.set("hours", String(hours));
        return requestJson(url.pathname + url.search)
            .then(function (payload) {
                renderTrend(payload.trend || {}, !!autoAnalyze);
            })
            .catch(function (error) {
                state.aiSignature = "";
                if (!silent) {
                    setNotice("warning", error.message || "命名空间趋势加载失败");
                }
            });
    }

    function loadSummary() {
        return requestJson(summaryUrl).then(function (payload) {
            state.summary = payload || {};
            renderSummary(state.summary);
        });
    }

    function loadNamespaces() {
        var url = new URL(namespacesUrl, window.location.origin);
        url.searchParams.set("hours", "24");
        return requestJson(url.pathname + url.search).then(function (payload) {
            var previousSelectedNamespace = state.selectedNamespace;
            state.namespaces = Array.isArray(payload.namespaces) ? payload.namespaces : [];
            if (state.selectedNamespace) {
                var exists = state.namespaces.some(function (item) {
                    return String(item.namespace || "") === state.selectedNamespace;
                });
                if (!exists) {
                    state.selectedNamespace = "";
                }
            }
            if (!state.selectedNamespace && state.namespaces.length) {
                state.selectedNamespace = String(state.namespaces[0].namespace || "");
            }
            var shouldAutoAnalyzeSelected = !!state.selectedNamespace && state.selectedNamespace !== previousSelectedNamespace;
            renderNamespaceTable();
            if (state.selectedNamespace) {
                return loadTrend(state.selectedNamespace, true, shouldAutoAnalyzeSelected);
            }
            renderTrend({
                namespace: "",
                hours: Number(trendHoursInput && trendHoursInput.value ? trendHoursInput.value : defaultTrendHours || 24),
                timestamps: [],
                series: { cpu_per: [], mem_per: [], pod: [] },
                last_point: {},
            }, false);
            state.aiSignature = "";
            stopAutoAiAnalysis();
            if (aiResultNode) {
                setAiResult("当前无可用命名空间，无法进行 AI 分析。", false);
            }
            return Promise.resolve();
        });
    }

    function loadNodes() {
        var url = new URL(nodesUrl, window.location.origin);
        url.searchParams.set("hours", "24");
        return requestJson(url.pathname + url.search).then(function (payload) {
            state.nodes = Array.isArray(payload.nodes) ? payload.nodes : [];
            renderNodeTable();
        });
    }

    function restartTimer() {
        if (refreshTimer) {
            window.clearInterval(refreshTimer);
            refreshTimer = null;
        }
        if (state.refreshSeconds > 0) {
            refreshTimer = window.setInterval(function () {
                refreshAll(false);
            }, state.refreshSeconds * 1000);
        }
    }

    function refreshAll(showNotice) {
        return Promise.all([loadSummary(), loadNamespaces(), loadNodes()])
            .then(function () {
                if (showNotice) {
                    setNotice("success", "K8S监控数据已更新");
                }
            })
            .catch(function (error) {
                setNotice("error", error.message || "K8S监控刷新失败", 5000);
            });
    }

    if (searchInput) {
        searchInput.addEventListener("input", renderNamespaceTable);
    }

    if (refreshBtn) {
        refreshBtn.addEventListener("click", function () {
            refreshAll(true);
        });
    }

    if (refreshIntervalInput) {
        refreshIntervalInput.value = String(state.refreshSeconds);
        refreshIntervalInput.addEventListener("change", function () {
            var selected = Number(refreshIntervalInput.value || "60");
            state.refreshSeconds = Number.isFinite(selected) && selected > 0 ? selected : 60;
            restartTimer();
            setNotice("success", "刷新周期已更新为 " + state.refreshSeconds + " 秒", 2200);
        });
    }

    if (trendHoursInput) {
        trendHoursInput.value = String(defaultTrendHours || 24);
        trendHoursInput.addEventListener("change", function () {
            if (state.selectedNamespace) {
                loadTrend(state.selectedNamespace, false, true);
            }
        });
    }

    if (namespaceBody) {
        namespaceBody.addEventListener("click", function (event) {
            var target = event.target;
            if (!(target instanceof Element)) {
                return;
            }
            var row = target.closest("tr[data-namespace]");
            if (!row) {
                return;
            }
            var namespace = row.getAttribute("data-namespace") || "";
            if (!namespace) {
                return;
            }
            state.selectedNamespace = namespace;
            renderNamespaceTable();
            loadTrend(namespace, false, true);
        });
    }

    if (nodeBody) {
        nodeBody.addEventListener("click", function (event) {
            var target = event.target;
            if (!(target instanceof Element)) {
                return;
            }
            var row = target.closest("tr[data-node-ip]");
            if (!row) {
                return;
            }
            var nodeIp = row.getAttribute("data-node-ip") || "";
            if (!nodeIp) {
                return;
            }
            openNodeModal(nodeIp);
        });
    }

    function clearNamespaceTrendHover() {
        if (!state.trendData) {
            hideTrendTooltip();
            return;
        }
        if (state.hoverIndex === -1 && (!trendTooltipNode || trendTooltipNode.hidden)) {
            return;
        }
        hideTrendTooltip();
        drawTrend(state.trendData);
    }

    function updateNamespaceTrendHoverFromEvent(event) {
        if (!trendCanvas || !state.chartModel || !state.trendData) {
            hideTrendTooltip();
            return;
        }
        var rect = trendCanvas.getBoundingClientRect();
        if (
            event.clientX < rect.left ||
            event.clientX > rect.right ||
            event.clientY < rect.top ||
            event.clientY > rect.bottom
        ) {
            clearNamespaceTrendHover();
            return;
        }
        var model = state.chartModel;
        var point = canvasCoordsFromEvent(trendCanvas, event, model);
        var index = hoverIndexByNearestX(model, point.x);
        if (index < 0) {
            clearNamespaceTrendHover();
            return;
        }
        state.trendPreviewIndex = -1;
        state.trendPreviewX = -1;
        if (state.hoverIndex !== index) {
            state.hoverIndex = index;
            drawTrend(state.trendData);
        } else {
            showTrendTooltipForIndex(index);
        }
    }

    if (trendChartWrapNode && trendCanvas) {
        trendChartWrapNode.addEventListener("mousemove", updateNamespaceTrendHoverFromEvent);
        trendChartWrapNode.addEventListener("pointermove", updateNamespaceTrendHoverFromEvent);
        trendChartWrapNode.addEventListener("mouseleave", clearNamespaceTrendHover);
        trendChartWrapNode.addEventListener("pointerleave", clearNamespaceTrendHover);
    }

    function bindTrendTooltipGuards() {
        function bindGuard(wrapNode, tooltipNode, hideFn, resetFn) {
            if (!wrapNode) {
                return;
            }

            function handleGlobalPointer(event) {
                if (!tooltipNode || tooltipNode.hidden) {
                    return;
                }
                if (!event || typeof event.clientX !== "number" || typeof event.clientY !== "number") {
                    return;
                }
                var rect = wrapNode.getBoundingClientRect();
                var inside = (
                    event.clientX >= rect.left &&
                    event.clientX <= rect.right &&
                    event.clientY >= rect.top &&
                    event.clientY <= rect.bottom
                );
                if (!inside) {
                    resetFn();
                }
            }

            document.addEventListener("mousemove", handleGlobalPointer, true);
            document.addEventListener("pointermove", handleGlobalPointer, true);
            window.addEventListener("scroll", function () {
                if (!tooltipNode || tooltipNode.hidden) {
                    return;
                }
                resetFn();
            }, true);
        }

        bindGuard(trendChartWrapNode, trendTooltipNode, hideTrendTooltip, clearNamespaceTrendHover);
        bindGuard(nodeTrendChartWrapNode, nodeTrendTooltipNode, hideNodeTrendTooltip, clearNodeTrendHover);
    }

    if (nodeTrendHoursInput) {
        nodeTrendHoursInput.value = String(defaultTrendHours || 24);
        nodeTrendHoursInput.addEventListener("change", function () {
            if (state.selectedNodeIp && state.nodeModalOpen) {
                loadNodeTrend(state.selectedNodeIp, false, true);
            }
        });
    }

    Array.prototype.forEach.call(nodeModalCloseTriggers || [], function (trigger) {
        trigger.addEventListener("click", function () {
            closeNodeModal();
        });
    });

    function clearNodeTrendHover() {
        if (!state.nodeTrendData) {
            hideNodeTrendTooltip();
            return;
        }
        if (state.nodeTrendHoverIndex === -1 && (!nodeTrendTooltipNode || nodeTrendTooltipNode.hidden)) {
            return;
        }
        hideNodeTrendTooltip();
        drawNodeTrend(state.nodeTrendData);
    }

    function updateNodeTrendHoverFromEvent(event) {
        if (!nodeTrendCanvas || !state.nodeTrendChartModel || !state.nodeTrendData) {
            hideNodeTrendTooltip();
            return;
        }
        var rect = nodeTrendCanvas.getBoundingClientRect();
        if (
            event.clientX < rect.left ||
            event.clientX > rect.right ||
            event.clientY < rect.top ||
            event.clientY > rect.bottom
        ) {
            clearNodeTrendHover();
            return;
        }
        var model = state.nodeTrendChartModel;
        var point = canvasCoordsFromEvent(nodeTrendCanvas, event, model);
        var index = hoverIndexByNearestX(model, point.x);
        if (index < 0) {
            clearNodeTrendHover();
            return;
        }
        state.nodeTrendPreviewIndex = -1;
        state.nodeTrendPreviewX = -1;
        if (state.nodeTrendHoverIndex !== index) {
            state.nodeTrendHoverIndex = index;
            drawNodeTrend(state.nodeTrendData);
        } else {
            showNodeTrendTooltipForIndex(index);
        }
    }

    if (nodeTrendChartWrapNode && nodeTrendCanvas) {
        nodeTrendChartWrapNode.addEventListener("mousemove", updateNodeTrendHoverFromEvent);
        nodeTrendChartWrapNode.addEventListener("pointermove", updateNodeTrendHoverFromEvent);
        nodeTrendChartWrapNode.addEventListener("mouseleave", clearNodeTrendHover);
        nodeTrendChartWrapNode.addEventListener("pointerleave", clearNodeTrendHover);
    }

    Array.prototype.forEach.call(sortButtons || [], function (button) {
        button.addEventListener("click", function () {
            var key = button.getAttribute("data-k8smon-sort-key") || "";
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
            renderNamespaceTable();
        });
    });

    bindTrendTooltipGuards();

    if (aiResultNode && !aiStreamUrlTemplate) {
        setAiResult("AI分析接口未配置，请先设置 MONITORING_AI 配置。", false);
    } else if (aiResultNode) {
        setAiResult("点击命名空间名称后自动开始分析。", false);
    }
    if (nodeAiResultNode && !nodeAiStreamUrlTemplate) {
        setNodeAiResult("AI分析接口未配置，请先设置 MONITORING_AI 配置。", false);
    } else if (nodeAiResultNode) {
        setNodeAiResult("打开节点后自动开始分析。", false);
    }

    window.addEventListener("resize", function () {
        if (state.trendData) {
            hideTrendTooltip();
            drawTrend(state.trendData);
        }
        if (state.nodeTrendData) {
            hideNodeTrendTooltip();
            drawNodeTrend(state.nodeTrendData);
        }
    });
    window.addEventListener("beforeunload", function () {
        stopAutoAiAnalysis();
        stopNodeAutoAiAnalysis();
    });
    window.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && state.nodeModalOpen) {
            closeNodeModal();
        }
    });

    updateSortButtons();
    restartTimer();
    refreshAll(false);
})();
