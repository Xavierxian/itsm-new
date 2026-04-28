(function () {
    "use strict";

    var addButton = document.getElementById("qualification-add-detail");
    var body = document.getElementById("qualification-detail-body");
    var template = document.getElementById("qualification-detail-empty-template");
    var totalForms =
        document.getElementById("id_details-TOTAL_FORMS") ||
        document.querySelector('input[name$="-TOTAL_FORMS"]');

    if (!addButton || !body || !template || !totalForms) {
        return;
    }

    function markRowDeleted(row) {
        if (!row) {
            return;
        }
        var deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
        if (deleteInput) {
            deleteInput.checked = true;
        }
        row.hidden = true;
        row.classList.add("is-marked-delete");
    }

    function bindRemoveButton(row) {
        var removeButton = row.querySelector("[data-detail-remove]");
        if (!removeButton) {
            return;
        }
        removeButton.addEventListener("click", function () {
            markRowDeleted(row);
        });
    }

    function normalizeLocalDateTimeInput(input) {
        if (!input || input.value) {
            return;
        }
        var now = new Date();
        var offset = now.getTimezoneOffset() * 60000;
        var localIso = new Date(now.getTime() - offset).toISOString().slice(0, 16);
        input.value = localIso;
    }

    function bindExistingRows() {
        var rows = body.querySelectorAll("[data-detail-row]");
        Array.prototype.forEach.call(rows, function (row) {
            bindRemoveButton(row);
            var deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
            if (deleteInput && deleteInput.checked) {
                row.hidden = true;
                row.classList.add("is-marked-delete");
            }
        });
    }

    addButton.addEventListener("click", function () {
        var index = parseInt(totalForms.value, 10);
        if (Number.isNaN(index)) {
            return;
        }

        var emptyStateRow = body.querySelector("[data-detail-empty-state]");
        if (emptyStateRow && emptyStateRow.parentNode) {
            emptyStateRow.parentNode.removeChild(emptyStateRow);
        }

        var html = template.innerHTML.replace(/__prefix__/g, String(index));
        body.insertAdjacentHTML("beforeend", html);
        totalForms.value = String(index + 1);

        var newRow = body.querySelector('[data-form-index="' + index + '"]');
        if (!newRow) {
            return;
        }

        var createTimeInput = newRow.querySelector('input[name$="-create_time"]');
        normalizeLocalDateTimeInput(createTimeInput);
        bindRemoveButton(newRow);
    });

    bindExistingRows();
})();
