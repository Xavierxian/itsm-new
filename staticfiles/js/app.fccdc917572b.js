(function () {
    var shell = document.querySelector(".app-shell");
    var appMain = document.querySelector(".app-main-v2");
    var sidebarToggle = document.querySelector("[data-sidebar-toggle]");
    var sidebarDismiss = document.querySelector("[data-sidebar-dismiss]");
    var sidebarToggleText = document.querySelector(".sidebar-toggle-text-v2");
    var desktopBreakpoint = 980;

    function resetFixedViewportScroll() {
        // When the viewport is locked, always normalize to the very top.
        if (appMain) {
            appMain.scrollTop = 0;
            appMain.scrollLeft = 0;
        }
        var detailPanel = document.querySelector(".list-panel-v4-authdetailx");
        if (detailPanel) {
            detailPanel.scrollTop = 0;
            detailPanel.scrollLeft = 0;
        }
        if (document.documentElement) {
            document.documentElement.scrollTop = 0;
        }
        if (document.body) {
            document.body.scrollTop = 0;
        }
        window.scrollTo(0, 0);
    }

    if ("scrollRestoration" in window.history) {
        window.history.scrollRestoration = "manual";
    }

    function isMobileLayout() {
        return window.innerWidth <= desktopBreakpoint;
    }

    function updateBackdrop(isVisible) {
        if (!sidebarDismiss) {
            return;
        }
        if (isVisible) {
            sidebarDismiss.classList.add("is-visible");
        } else {
            sidebarDismiss.classList.remove("is-visible");
        }
    }

    function syncSidebarMode() {
        if (!shell) {
            return;
        }
        if (isMobileLayout()) {
            if (sidebarToggleText) {
                sidebarToggleText.textContent = "打开导航";
            }
            if (sidebarToggle) {
                sidebarToggle.setAttribute("aria-label", "打开导航");
            }
        } else {
            updateBackdrop(false);
            shell.classList.remove("sidebar-open");
        }
    }

    if (sidebarToggle && shell) {
        sidebarToggle.addEventListener("click", function () {
            if (isMobileLayout()) {
                var isOpen = shell.classList.contains("sidebar-open");
                if (isOpen) {
                    shell.classList.remove("sidebar-open");
                    updateBackdrop(false);
                } else {
                    shell.classList.add("sidebar-open");
                    updateBackdrop(true);
                }
            }
        });
    }

    if (sidebarDismiss && shell) {
        sidebarDismiss.addEventListener("click", function () {
            shell.classList.remove("sidebar-open");
            updateBackdrop(false);
        });
    }

    var groups = document.querySelectorAll("[data-nav-group]");
    Array.prototype.forEach.call(groups, function (group) {
        var trigger = group.querySelector("[data-nav-trigger]");
        var body = group.querySelector(".nav-group-body");
        var hasActive = !!group.querySelector(".nav-link.is-active");

        if (!body) {
            return;
        }

        if (hasActive) {
            group.classList.add("is-open");
            body.hidden = false;
        } else {
            group.classList.remove("is-open");
            body.hidden = true;
        }

        if (trigger) {
            trigger.addEventListener("click", function () {
                var isOpen = group.classList.contains("is-open");
                if (isOpen) {
                    group.classList.remove("is-open");
                    body.hidden = true;
                } else {
                    group.classList.add("is-open");
                    body.hidden = false;
                }
            });
        }
    });

    var autoResetSearchForms = document.querySelectorAll("[data-auto-reset-search]");
    Array.prototype.forEach.call(autoResetSearchForms, function (form) {
        var input = form.querySelector("[data-auto-reset-input]");
        if (!input) {
            return;
        }

        var previousValue = input.value.trim();
        input.addEventListener("input", function () {
            var currentValue = input.value.trim();
            if (previousValue && !currentValue) {
                if (typeof form.requestSubmit === "function") {
                    form.requestSubmit();
                } else {
                    form.submit();
                }
            }
            previousValue = currentValue;
        });
    });

    var autoSubmitSelects = document.querySelectorAll("[data-auto-submit-select]");
    Array.prototype.forEach.call(autoSubmitSelects, function (select) {
        var form = select.form;
        if (!form) {
            return;
        }
        select.addEventListener("change", function () {
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit();
            } else {
                form.submit();
            }
        });
    });

    var toasts = document.querySelectorAll(".toast");
    Array.prototype.forEach.call(toasts, function (toast) {
        if (toast.classList.contains("toast-error")) {
            return;
        }

        window.setTimeout(function () {
            toast.classList.add("is-dismissing");
            window.setTimeout(function () {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 260);
        }, 2000);
    });

    var userMenus = document.querySelectorAll("[data-user-menu]");
    Array.prototype.forEach.call(userMenus, function (menu) {
        var trigger = menu.querySelector("[data-user-menu-trigger]");
        var panel = menu.querySelector("[data-user-menu-panel]");
        if (!trigger || !panel) {
            return;
        }

        function setOpen(isOpen) {
            menu.classList.toggle("is-open", isOpen);
            panel.hidden = !isOpen;
            trigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
        }

        trigger.addEventListener("click", function () {
            setOpen(!menu.classList.contains("is-open"));
        });

        document.addEventListener("click", function (event) {
            if (!menu.contains(event.target)) {
                setOpen(false);
            }
        });
    });

    function bindFormConfirmModal() {
        var form = document.querySelector(".editor-form[data-submit-label]");
        var modal = document.getElementById("action-confirm-modal");
        if (!form || !modal) {
            return;
        }

        var titleEl = document.getElementById("confirm-modal-title");
        var messageEl = document.getElementById("confirm-modal-message");
        var cancelBtn = document.getElementById("confirm-modal-cancel");
        var confirmBtn = document.getElementById("confirm-modal-confirm");
        var closeMask = modal.querySelector("[data-modal-close]");
        var triggerButtons = form.querySelectorAll(".js-action-trigger");
        if (!titleEl || !messageEl || !cancelBtn || !confirmBtn || !triggerButtons.length) {
            return;
        }

        var submitLabel = form.getAttribute("data-submit-label") || "提交";
        var deleteConfirmText = form.getAttribute("data-delete-confirm") || "确认删除这条记录吗？";
        var pendingAction = "submit";
        var pendingLabel = submitLabel;

        function setDeleteActionField(enabled) {
            var field = form.querySelector("input[name=\"_action\"][data-confirm-injected=\"1\"]");
            if (enabled) {
                if (!field) {
                    field = document.createElement("input");
                    field.type = "hidden";
                    field.name = "_action";
                    field.setAttribute("data-confirm-injected", "1");
                    form.appendChild(field);
                }
                field.value = "delete";
                return;
            }
            if (field && field.parentNode) {
                field.parentNode.removeChild(field);
            }
        }

        function openModal(action, label) {
            pendingAction = action || "submit";
            pendingLabel = label || submitLabel;
            if (pendingAction === "delete") {
                titleEl.textContent = "确认删除";
                messageEl.textContent = deleteConfirmText;
                confirmBtn.textContent = "确认删除";
                confirmBtn.classList.remove("primary-button");
                confirmBtn.classList.add("danger-button");
            } else {
                titleEl.textContent = "确认" + pendingLabel;
                messageEl.textContent = "确认要" + pendingLabel + "当前内容吗？";
                confirmBtn.textContent = "确认" + pendingLabel;
                confirmBtn.classList.remove("danger-button");
                confirmBtn.classList.add("primary-button");
            }
            modal.hidden = false;
            document.body.classList.add("modal-open");
        }

        function closeModal() {
            modal.hidden = true;
            document.body.classList.remove("modal-open");
        }

        Array.prototype.forEach.call(triggerButtons, function (button) {
            button.addEventListener("click", function () {
                var action = button.getAttribute("data-action") || "submit";
                var label = button.getAttribute("data-label") || submitLabel;
                openModal(action, label);
            });
        });

        form.addEventListener("submit", function (event) {
            if (form.getAttribute("data-confirm-accepted") === "1") {
                form.removeAttribute("data-confirm-accepted");
                return;
            }
            event.preventDefault();
            openModal("submit", submitLabel);
        });

        confirmBtn.addEventListener("click", function () {
            setDeleteActionField(pendingAction === "delete");
            form.setAttribute("data-confirm-accepted", "1");
            closeModal();
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit();
            } else {
                form.submit();
            }
        });

        cancelBtn.addEventListener("click", closeModal);
        if (closeMask) {
            closeMask.addEventListener("click", closeModal);
        }
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && !modal.hidden) {
                closeModal();
            }
        });
    }

    function bindCopyTextButtons() {
        var copyButtons = document.querySelectorAll("[data-copy-text]");
        if (!copyButtons.length) {
            return;
        }

        function showCopied(button, ok) {
            var defaultLabel = button.getAttribute("data-copy-label-default") || "复制";
            var successLabel = button.getAttribute("data-copy-label-success") || "已复制";
            var failedLabel = "复制失败";
            button.textContent = ok ? successLabel : failedLabel;
            window.setTimeout(function () {
                button.textContent = defaultLabel;
            }, 1200);
        }

        function fallbackCopyText(value) {
            var fallback = document.createElement("textarea");
            fallback.value = value;
            fallback.setAttribute("readonly", "readonly");
            fallback.style.position = "absolute";
            fallback.style.left = "-9999px";
            document.body.appendChild(fallback);
            fallback.focus();
            fallback.select();
            var ok = false;
            try {
                ok = document.execCommand("copy");
            } catch (e) {
                ok = false;
            }
            document.body.removeChild(fallback);
            return ok;
        }

        Array.prototype.forEach.call(copyButtons, function (button) {
            button.addEventListener("click", function () {
                var value = button.getAttribute("data-copy-text") || "";
                if (!value) {
                    return;
                }

                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(value).then(
                        function () {
                            showCopied(button, true);
                        },
                        function () {
                            var ok = fallbackCopyText(value);
                            showCopied(button, ok);
                        }
                    );
                    return;
                }

                var ok = fallbackCopyText(value);
                showCopied(button, ok);
            });
        });
    }

    function bindAuthorizationDetailSuggest() {
        var form = document.getElementById("auth-detail-search-form");
        var input = document.getElementById("auth-detail-search");
        var panel = document.getElementById("auth-detail-suggest");
        var suggestUrl = form ? form.getAttribute("data-suggest-url") : "";
        if (!form || !input || !panel || !suggestUrl) {
            return;
        }

        var debounceTimer = null;
        var requestSerial = 0;
        var activeIndex = -1;

        function closePanel() {
            panel.hidden = true;
            panel.innerHTML = "";
            activeIndex = -1;
        }

        function submitByName(name) {
            input.value = name || "";
            if (typeof form.requestSubmit === "function") {
                form.requestSubmit();
            } else {
                form.submit();
            }
        }

        function renderSuggestions(items) {
            panel.innerHTML = "";
            activeIndex = -1;
            if (!items || !items.length) {
                closePanel();
                return;
            }
            items.forEach(function (item, index) {
                var option = document.createElement("button");
                option.type = "button";
                option.className = "auth-detail-suggest-item";
                option.setAttribute("data-index", String(index));
                option.innerHTML =
                    "<strong>" + (item.name || "-") + "</strong>" +
                    "<span># " + (item.code || "-") + " <em></em> " + (item.org_code || "-") + "</span>";
                option.addEventListener("mousedown", function (event) {
                    event.preventDefault();
                });
                option.addEventListener("click", function () {
                    submitByName(item.name || "");
                });
                panel.appendChild(option);
            });
            panel.hidden = false;
        }

        function highlight(index) {
            var items = panel.querySelectorAll(".auth-detail-suggest-item");
            if (!items.length) {
                activeIndex = -1;
                return;
            }
            if (index < 0) {
                index = items.length - 1;
            } else if (index >= items.length) {
                index = 0;
            }
            activeIndex = index;
            Array.prototype.forEach.call(items, function (item, itemIndex) {
                item.classList.toggle("is-active", itemIndex === activeIndex);
            });
        }

        function fetchSuggestions(keyword) {
            requestSerial += 1;
            var currentSerial = requestSerial;
            var url = new URL(suggestUrl, window.location.origin);
            url.searchParams.set("q", keyword);
            fetch(url.toString(), {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                credentials: "same-origin",
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error("request failed");
                    }
                    return response.json();
                })
                .then(function (data) {
                    if (currentSerial !== requestSerial) {
                        return;
                    }
                    renderSuggestions((data && data.items) || []);
                })
                .catch(function () {
                    closePanel();
                });
        }

        function navigateWithKeyword(keyword) {
            var target = new URL(window.location.href);
            if (keyword) {
                target.searchParams.set("q", keyword);
            } else {
                target.searchParams.delete("q");
            }
            window.location.href = target.pathname + (target.search ? target.search : "");
        }

        form.addEventListener("submit", function (event) {
            event.preventDefault();
            navigateWithKeyword(input.value.trim());
        });

        input.addEventListener("input", function () {
            var keyword = input.value.trim();
            if (debounceTimer) {
                clearTimeout(debounceTimer);
            }
            if (!keyword) {
                closePanel();
                if (new URL(window.location.href).searchParams.has("q")) {
                    navigateWithKeyword("");
                }
                return;
            }
            debounceTimer = window.setTimeout(function () {
                fetchSuggestions(keyword);
            }, 180);
        });

        input.addEventListener("keydown", function (event) {
            if (panel.hidden) {
                return;
            }
            if (event.key === "ArrowDown") {
                event.preventDefault();
                highlight(activeIndex + 1);
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                highlight(activeIndex - 1);
            } else if (event.key === "Enter") {
                if (activeIndex >= 0) {
                    var items = panel.querySelectorAll(".auth-detail-suggest-item");
                    if (items[activeIndex]) {
                        event.preventDefault();
                        items[activeIndex].click();
                    }
                }
            } else if (event.key === "Escape") {
                closePanel();
            }
        });

        document.addEventListener("click", function (event) {
            if (!form.contains(event.target) && !panel.contains(event.target)) {
                closePanel();
            }
        });
    }

    function bindEnhancedMultiSelect() {
        var selects = document.querySelectorAll(
            ".editor-form .field select[multiple][data-enhanced-multiselect=\"1\"]"
        );
        if (!selects.length) {
            return;
        }

        Array.prototype.forEach.call(selects, function (select) {
            if (select.getAttribute("data-enhanced-initialized") === "1") {
                return;
            }
            select.setAttribute("data-enhanced-initialized", "1");
            select.classList.add("is-native-hidden");

            var wrapper = document.createElement("div");
            wrapper.className = "enhanced-multiselect-v2";

            var selectedBox = document.createElement("div");
            selectedBox.className = "enhanced-multiselect-selected-v2";

            var searchInput = document.createElement("input");
            searchInput.type = "search";
            searchInput.className = "enhanced-multiselect-search-v2";
            searchInput.placeholder = "搜索并勾选角色";
            searchInput.setAttribute("aria-label", "搜索角色");

            var optionsBox = document.createElement("div");
            optionsBox.className = "enhanced-multiselect-options-v2";

            wrapper.appendChild(selectedBox);
            wrapper.appendChild(searchInput);
            wrapper.appendChild(optionsBox);
            select.insertAdjacentElement("afterend", wrapper);

            function render(keyword) {
                var query = (keyword || "").trim().toLowerCase();
                selectedBox.innerHTML = "";
                optionsBox.innerHTML = "";

                var hasSelected = false;
                var visibleCount = 0;

                Array.prototype.forEach.call(select.options, function (option) {
                    var text = (option.textContent || "").trim();
                    var haystack = (text + " " + String(option.value || "")).toLowerCase();

                    if (option.selected) {
                        hasSelected = true;
                        var chip = document.createElement("button");
                        chip.type = "button";
                        chip.className = "enhanced-multiselect-chip-v2";
                        chip.textContent = text;
                        chip.title = "取消选择 " + text;
                        chip.addEventListener("click", function () {
                            option.selected = false;
                            render(searchInput.value);
                        });
                        selectedBox.appendChild(chip);
                    }

                    if (query && haystack.indexOf(query) === -1) {
                        return;
                    }

                    visibleCount += 1;
                    var row = document.createElement("label");
                    row.className = "enhanced-multiselect-option-v2";

                    var checkbox = document.createElement("input");
                    checkbox.type = "checkbox";
                    checkbox.checked = option.selected;
                    checkbox.addEventListener("change", function () {
                        option.selected = checkbox.checked;
                        render(searchInput.value);
                    });

                    var label = document.createElement("span");
                    label.textContent = text || String(option.value || "");

                    row.appendChild(checkbox);
                    row.appendChild(label);
                    optionsBox.appendChild(row);
                });

                if (!hasSelected) {
                    var selectedEmpty = document.createElement("span");
                    selectedEmpty.className = "enhanced-multiselect-empty-v2";
                    selectedEmpty.textContent = "未选择角色";
                    selectedBox.appendChild(selectedEmpty);
                }

                if (!visibleCount) {
                    var optionsEmpty = document.createElement("span");
                    optionsEmpty.className = "enhanced-multiselect-empty-v2";
                    optionsEmpty.textContent = "没有匹配结果";
                    optionsBox.appendChild(optionsEmpty);
                }
            }

            searchInput.addEventListener("input", function () {
                render(searchInput.value);
            });
            select.addEventListener("change", function () {
                render(searchInput.value);
            });

            render("");
        });
    }

    function bindEnhancedPermissionSelect() {
        var form = document.querySelector(".role-editor-form-v2");
        var groupsRoot = document.getElementById("role-permission-groups-v2");
        var searchInput = document.getElementById("role-permission-search-v2");
        if (!form || !groupsRoot || !searchInput) {
            return;
        }

        var select = form.querySelector("select[multiple][data-enhanced-permission-select=\"1\"]");
        if (!select || select.getAttribute("data-enhanced-initialized") === "1") {
            return;
        }
        select.setAttribute("data-enhanced-initialized", "1");
        select.classList.add("is-native-hidden");

        var items = [];
        Array.prototype.forEach.call(select.options, function (option) {
            var raw = (option.textContent || "").trim();
            var parts = raw.split("|").map(function (part) {
                return part.trim();
            }).filter(Boolean);
            var app = parts[0] || "Other";
            var resource = parts[1] || "General";
            var action = parts.length > 2 ? parts.slice(2).join(" | ") : raw;
            var haystack = (app + " " + resource + " " + action + " " + String(option.value || ""))
                .toLowerCase();
            items.push({
                option: option,
                app: app,
                resource: resource,
                action: action || String(option.value || ""),
                haystack: haystack,
                row: null,
                checkbox: null,
                group: null,
            });
        });

        var groupMap = {};
        items.forEach(function (item) {
            if (!groupMap[item.app]) {
                groupMap[item.app] = [];
            }
            groupMap[item.app].push(item);
        });

        function updateCounters() {
            var selectedCount = 0;
            var visibleCount = 0;
            items.forEach(function (item) {
                if (item.option.selected) {
                    selectedCount += 1;
                }
                if (item.row && !item.row.hidden) {
                    visibleCount += 1;
                }
            });

            var selectedTargets = document.querySelectorAll("[data-role-permission-selected-count]");
            Array.prototype.forEach.call(selectedTargets, function (node) {
                node.textContent = String(selectedCount);
            });
            var visibleTargets = document.querySelectorAll("[data-role-permission-visible-count]");
            Array.prototype.forEach.call(visibleTargets, function (node) {
                node.textContent = String(visibleCount);
            });

            Object.keys(groupMap).forEach(function (groupName) {
                var groupItems = groupMap[groupName];
                var selectedInGroup = groupItems.filter(function (it) { return it.option.selected; }).length;
                if (groupItems.length && groupItems[0].group) {
                    var badge = groupItems[0].group.querySelector("[data-group-selected-count]");
                    if (badge) {
                        badge.textContent = selectedInGroup + "/" + groupItems.length;
                    }
                }
            });
        }

        function renderGroups() {
            groupsRoot.innerHTML = "";
            Object.keys(groupMap).forEach(function (groupName) {
                var groupItems = groupMap[groupName];
                var group = document.createElement("section");
                group.className = "role-perm-group-v2";

                var head = document.createElement("div");
                head.className = "role-perm-group-head-v2";

                var title = document.createElement("h5");
                title.textContent = groupName;

                var badge = document.createElement("span");
                badge.className = "role-perm-group-badge-v2";
                badge.setAttribute("data-group-selected-count", "1");
                badge.textContent = "0/" + groupItems.length;

                var actions = document.createElement("div");
                actions.className = "role-perm-group-actions-v2";

                var selectAll = document.createElement("button");
                selectAll.type = "button";
                selectAll.className = "secondary-button";
                selectAll.textContent = "全选";

                var clearAll = document.createElement("button");
                clearAll.type = "button";
                clearAll.className = "secondary-button";
                clearAll.textContent = "清空";

                actions.appendChild(selectAll);
                actions.appendChild(clearAll);

                head.appendChild(title);
                head.appendChild(badge);
                head.appendChild(actions);
                group.appendChild(head);

                var body = document.createElement("div");
                body.className = "role-perm-group-body-v2";
                group.appendChild(body);

                groupItems.forEach(function (item) {
                    var row = document.createElement("label");
                    row.className = "role-perm-item-v2";

                    var checkbox = document.createElement("input");
                    checkbox.type = "checkbox";
                    checkbox.checked = item.option.selected;
                    checkbox.addEventListener("change", function () {
                        item.option.selected = checkbox.checked;
                        updateCounters();
                    });

                    var copy = document.createElement("div");
                    copy.className = "role-perm-copy-v2";

                    var strong = document.createElement("strong");
                    strong.textContent = item.resource;

                    var span = document.createElement("span");
                    span.textContent = item.action;

                    copy.appendChild(strong);
                    copy.appendChild(span);
                    row.appendChild(checkbox);
                    row.appendChild(copy);
                    body.appendChild(row);

                    item.row = row;
                    item.checkbox = checkbox;
                    item.group = group;
                });

                selectAll.addEventListener("click", function () {
                    groupItems.forEach(function (item) {
                        if (!item.row.hidden) {
                            item.option.selected = true;
                            item.checkbox.checked = true;
                        }
                    });
                    updateCounters();
                });

                clearAll.addEventListener("click", function () {
                    groupItems.forEach(function (item) {
                        if (!item.row.hidden) {
                            item.option.selected = false;
                            item.checkbox.checked = false;
                        }
                    });
                    updateCounters();
                });

                groupsRoot.appendChild(group);
            });
        }

        function applyFilter(query) {
            var keyword = (query || "").trim().toLowerCase();
            var hasKeyword = keyword.length > 0;
            var totalVisible = 0;
            Object.keys(groupMap).forEach(function (groupName) {
                var groupItems = groupMap[groupName];
                var visibleInGroup = 0;
                groupItems.forEach(function (item) {
                    var matched = !hasKeyword || item.haystack.indexOf(keyword) !== -1;
                    item.row.hidden = !matched;
                    if (matched) {
                        visibleInGroup += 1;
                        totalVisible += 1;
                    }
                });
                if (groupItems.length && groupItems[0].group) {
                    groupItems[0].group.hidden = hasKeyword && visibleInGroup === 0;
                }
            });

            // Fallback: when there is no keyword, never leave the panel empty.
            if (!hasKeyword && totalVisible === 0) {
                items.forEach(function (item) {
                    item.row.hidden = false;
                    if (item.group) {
                        item.group.hidden = false;
                    }
                });
            }

            updateCounters();
        }

        function toggleVisible(checked) {
            items.forEach(function (item) {
                if (!item.row.hidden) {
                    item.option.selected = checked;
                    item.checkbox.checked = checked;
                }
            });
            updateCounters();
        }

        var actionButtons = form.querySelectorAll("[data-role-perm-action]");
        Array.prototype.forEach.call(actionButtons, function (button) {
            button.addEventListener("click", function () {
                var action = button.getAttribute("data-role-perm-action");
                if (action === "select-visible") {
                    toggleVisible(true);
                } else if (action === "clear-visible") {
                    toggleVisible(false);
                }
            });
        });

        searchInput.addEventListener("input", function () {
            applyFilter(searchInput.value);
        });

        renderGroups();
        applyFilter("");
    }

    function bindRenderedPermissionSelect() {
        var form = document.querySelector(".role-editor-form-v2");
        var searchInput = document.getElementById("role-permission-search-v2");
        if (!form || !searchInput) {
            return;
        }

        var groups = form.querySelectorAll("[data-role-perm-group]");
        var items = form.querySelectorAll("[data-role-perm-item]");
        if (!groups.length || !items.length) {
            return;
        }

        function updateCounters() {
            var selectedCount = 0;
            var visibleCount = 0;

            Array.prototype.forEach.call(items, function (item) {
                var checkbox = item.querySelector("[data-role-perm-checkbox]");
                if (checkbox && checkbox.checked) {
                    selectedCount += 1;
                }
                if (!item.hidden) {
                    visibleCount += 1;
                }
            });

            var selectedTargets = document.querySelectorAll("[data-role-permission-selected-count]");
            Array.prototype.forEach.call(selectedTargets, function (node) {
                node.textContent = String(selectedCount);
            });

            var visibleTargets = document.querySelectorAll("[data-role-permission-visible-count]");
            Array.prototype.forEach.call(visibleTargets, function (node) {
                node.textContent = String(visibleCount);
            });

            Array.prototype.forEach.call(groups, function (group) {
                var groupItems = group.querySelectorAll("[data-role-perm-item]");
                var selectedInGroup = 0;

                Array.prototype.forEach.call(groupItems, function (item) {
                    var checkbox = item.querySelector("[data-role-perm-checkbox]");
                    if (checkbox && checkbox.checked) {
                        selectedInGroup += 1;
                    }
                });

                var badge = group.querySelector("[data-group-selected-count]");
                if (badge) {
                    badge.textContent = selectedInGroup + "/" + groupItems.length;
                }
            });
        }

        function applyFilter(query) {
            var keyword = (query || "").trim().toLowerCase();
            var hasKeyword = keyword.length > 0;

            Array.prototype.forEach.call(groups, function (group) {
                var groupItems = group.querySelectorAll("[data-role-perm-item]");
                var visibleInGroup = 0;

                Array.prototype.forEach.call(groupItems, function (item) {
                    var haystack = item.getAttribute("data-perm-search") || "";
                    var matched = !hasKeyword || haystack.indexOf(keyword) !== -1;
                    item.hidden = !matched;
                    if (matched) {
                        visibleInGroup += 1;
                    }
                });

                group.hidden = hasKeyword && visibleInGroup === 0;
            });

            updateCounters();
        }

        function toggleVisible(checked) {
            Array.prototype.forEach.call(items, function (item) {
                if (item.hidden) {
                    return;
                }
                var checkbox = item.querySelector("[data-role-perm-checkbox]");
                if (checkbox) {
                    checkbox.checked = checked;
                }
            });
            updateCounters();
        }

        Array.prototype.forEach.call(items, function (item) {
            var checkbox = item.querySelector("[data-role-perm-checkbox]");
            if (!checkbox) {
                return;
            }
            checkbox.addEventListener("change", updateCounters);
        });

        var actionButtons = form.querySelectorAll("[data-role-perm-action]");
        Array.prototype.forEach.call(actionButtons, function (button) {
            button.addEventListener("click", function () {
                var action = button.getAttribute("data-role-perm-action");
                if (action === "select-visible") {
                    toggleVisible(true);
                } else if (action === "clear-visible") {
                    toggleVisible(false);
                }
            });
        });

        Array.prototype.forEach.call(groups, function (group) {
            var groupButtons = group.querySelectorAll("[data-role-group-action]");
            Array.prototype.forEach.call(groupButtons, function (button) {
                button.addEventListener("click", function () {
                    var action = button.getAttribute("data-role-group-action");
                    var groupItems = group.querySelectorAll("[data-role-perm-item]");

                    Array.prototype.forEach.call(groupItems, function (item) {
                        if (item.hidden) {
                            return;
                        }
                        var checkbox = item.querySelector("[data-role-perm-checkbox]");
                        if (checkbox) {
                            checkbox.checked = action === "select";
                        }
                    });

                    updateCounters();
                });
            });
        });

        searchInput.addEventListener("input", function () {
            applyFilter(searchInput.value);
        });

        applyFilter("");
    }

    window.addEventListener("resize", syncSidebarMode);
    window.addEventListener("pageshow", resetFixedViewportScroll);
    window.setTimeout(resetFixedViewportScroll, 0);
    syncSidebarMode();
    bindFormConfirmModal();
    bindCopyTextButtons();
    bindAuthorizationDetailSuggest();
    bindEnhancedMultiSelect();
    bindRenderedPermissionSelect();
})();
