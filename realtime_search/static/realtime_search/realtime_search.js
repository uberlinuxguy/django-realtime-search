/*
 * django-realtime-search
 *
 * Filters a Django admin changelist as you type in its search box. Each
 * search fetches the normal changelist URL (so ModelAdmin.search_fields,
 * get_search_results(), filters, ordering and permissions all apply
 * unchanged) and swaps the result list into the current page.
 */
(function () {
    "use strict";

    function ready(fn) {
        if (document.readyState !== "loading") {
            fn();
        } else {
            document.addEventListener("DOMContentLoaded", fn);
        }
    }

    function replaceElement(oldEl, newEl) {
        oldEl.parentNode.replaceChild(document.importNode(newEl, true), oldEl);
    }

    function init() {
        var configEl = document.getElementById("realtime-search-config");
        var searchForm = document.getElementById("changelist-search");
        var input = document.getElementById("searchbar");
        var changelist = document.getElementById("changelist");
        if (!configEl || !searchForm || !input || !changelist) {
            return;
        }

        var config;
        try {
            config = JSON.parse(configEl.textContent);
        } catch (e) {
            return;
        }

        var timer = null;
        var controller = null;
        var requestSeq = 0;
        var lastQuery = input.value;
        // True once a list_editable field is changed. Live updates are then
        // paused so unsaved edits aren't thrown away.
        var hasUnsavedEdits = false;

        // Browser autocomplete dropdowns cover the results being filtered.
        input.setAttribute("autocomplete", "off");

        var liveRegion = document.createElement("div");
        liveRegion.className = "realtime-search-sr-only";
        liveRegion.setAttribute("role", "status");
        liveRegion.setAttribute("aria-live", "polite");
        searchForm.appendChild(liveRegion);

        renderFilterHints();

        changelist.addEventListener("change", function (event) {
            var target = event.target;
            if (
                target.closest &&
                target.closest("#result_list") &&
                !target.classList.contains("action-select") &&
                target.id !== "action-toggle"
            ) {
                hasUnsavedEdits = true;
            }
        });

        input.addEventListener("input", function () {
            clearTimeout(timer);
            timer = setTimeout(function () {
                search(false);
            }, config.debounceMs);
        });

        input.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && input.value) {
                input.value = "";
                clearTimeout(timer);
                search(false);
            }
        });

        searchForm.addEventListener("submit", function (event) {
            if (hasUnsavedEdits) {
                return; // Fall back to a normal page load.
            }
            event.preventDefault();
            clearTimeout(timer);
            search(true);
        });

        // "Filters: author: in_print: ..." - clicking one adds it to the box.
        function renderFilterHints() {
            if (!config.filters || !config.filters.length) {
                return;
            }
            var container = document.createElement("div");
            container.className = "realtime-search-filters";
            container.appendChild(document.createTextNode("Filters: "));
            config.filters.forEach(function (filter) {
                var button = document.createElement("button");
                button.type = "button";
                button.textContent = filter.key + ":";
                button.title = "e.g. " + filter.example;
                button.addEventListener("click", function () {
                    var value = input.value;
                    if (value && !/\s$/.test(value)) {
                        value += " ";
                    }
                    input.value = value + filter.key + ":";
                    input.focus();
                    input.setSelectionRange(input.value.length, input.value.length);
                });
                container.appendChild(button);
            });
            searchForm.appendChild(container);
        }

        function buildUrl(query) {
            var params = new URLSearchParams();
            // The search form carries the current filters/ordering as
            // hidden inputs, so they're preserved.
            var elements = searchForm.elements;
            for (var i = 0; i < elements.length; i++) {
                var el = elements[i];
                if (!el.name || el === input || el.type === "submit") {
                    continue;
                }
                params.append(el.name, el.value);
            }
            params.delete("p"); // A new search starts at page 1.
            if (query) {
                params.set(input.name, query);
            }
            var qs = params.toString();
            return window.location.pathname + (qs ? "?" + qs : "");
        }

        function search(force) {
            var query = input.value;
            if (!force && query === lastQuery) {
                return;
            }
            if (!force && query && query.trim().length < config.minChars) {
                return;
            }
            if (hasUnsavedEdits) {
                return;
            }

            var url = buildUrl(query);
            var seq = ++requestSeq;
            if (controller) {
                controller.abort();
            }
            controller = window.AbortController ? new AbortController() : null;

            changelist.classList.add("realtime-search-loading");
            input.setAttribute("aria-busy", "true");

            fetch(url, {
                credentials: "same-origin",
                headers: { "X-Requested-With": "XMLHttpRequest" },
                signal: controller ? controller.signal : undefined,
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error("HTTP " + response.status);
                    }
                    return response.text();
                })
                .then(function (html) {
                    if (seq !== requestSeq) {
                        return; // A newer search superseded this one.
                    }
                    var doc = new DOMParser().parseFromString(html, "text/html");
                    if (!applyResults(doc)) {
                        // Not a changelist (e.g. session expired and we were
                        // redirected to login): let the browser handle it.
                        window.location.assign(url);
                        return;
                    }
                    lastQuery = query;
                    window.history.replaceState(window.history.state, "", url);
                    document.dispatchEvent(
                        new CustomEvent("realtime-search:updated", {
                            detail: { query: query, url: url },
                        })
                    );
                })
                .catch(function (error) {
                    if (error && error.name === "AbortError") {
                        return;
                    }
                    if (seq === requestSeq) {
                        // Something went wrong; a full page load will at
                        // least show the user the error.
                        window.location.assign(url);
                    }
                })
                .then(function () {
                    if (seq === requestSeq) {
                        changelist.classList.remove("realtime-search-loading");
                        input.removeAttribute("aria-busy");
                    }
                });
        }

        function applyResults(doc) {
            var oldForm = document.getElementById("changelist-form");
            var newForm = doc.getElementById("changelist-form");
            if (!oldForm || !newForm) {
                return false;
            }
            replaceElement(oldForm, newForm);

            // Filter and date hierarchy links embed the search term.
            ["#changelist-filter", "#changelist .xfull", "#changelist nav.toplinks"].forEach(
                function (selector) {
                    var oldEl = document.querySelector(selector);
                    var newEl = doc.querySelector(selector);
                    if (oldEl && newEl) {
                        replaceElement(oldEl, newEl);
                    }
                }
            );

            // "N results (M total)" only appears while a search is active.
            var countSelector = "#changelist-search .small.quiet";
            var oldCount = document.querySelector(countSelector);
            var newCount = doc.querySelector(countSelector);
            if (oldCount && newCount) {
                replaceElement(oldCount, newCount);
            } else if (oldCount) {
                oldCount.parentNode.removeChild(oldCount);
            } else if (newCount) {
                var submit = searchForm.querySelector("input[type=submit]");
                var imported = document.importNode(newCount, true);
                if (submit && submit.parentNode) {
                    submit.parentNode.insertBefore(imported, submit.nextSibling);
                    submit.parentNode.insertBefore(document.createTextNode(" "), imported);
                } else {
                    searchForm.appendChild(imported);
                }
            }

            var announce = newCount || doc.querySelector("#changelist-form .paginator");
            liveRegion.textContent = announce
                ? announce.textContent.replace(/\s+/g, " ").trim()
                : "";

            hasUnsavedEdits = false;
            initActions();
            return true;
        }

        // Re-bind Django's admin actions (select-all checkbox, counter, etc.)
        // to the freshly inserted result list.
        function initActions() {
            var checkboxes = document.querySelectorAll("tr input.action-select");
            if (!checkboxes.length) {
                return;
            }
            if (typeof window.Actions === "function") {
                window.Actions(checkboxes);
            } else if (window.django && django.jQuery && django.jQuery.fn.actions) {
                django.jQuery(checkboxes).actions();
            }
        }
    }

    ready(init);
})();
