/* global document, window, Element, URL, fetch */
/* Login-required prompt: optional UI for restricted navigation; auth is enforced on the server. */
(() => {
    "use strict";

    const restrictedPages = new Map([
        ["/app", "your Account Dashboard"],
        ["/test-panel.html", "the User Flow Test Panel"],
        ["/upcoming-games.html", "upcoming NBA games and win estimates"],
        ["/upcoming_games.html", "upcoming NBA games and win estimates"]
    ]);
    let dialogOpen = false;
    let checkingAccess = false;

    const popupStyle = `
      .login-gate-backdrop {
        position: fixed;
        inset: 0;
        background: rgba(16, 27, 48, .66);
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 20px;
        z-index: 10000;
      }
      .login-gate-card {
        position: relative;
        background: #fff;
        color: #162238;
        width: 100%;
        max-width: 470px;
        border: 1px solid #e2e8f0;
        border-radius: 15px;
        padding: 28px;
        box-shadow: 0 22px 70px rgba(16, 27, 48, .22);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Arial, sans-serif;
        line-height: 1.55;
      }
      .login-gate-card .login-gate-eyebrow {
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: .16em;
        font-weight: 800;
        color: #2563eb;
        margin: 0 0 7px;
      }
      .login-gate-card h2 {
        font-size: 23px;
        line-height: 1.3;
        margin: 0 30px 12px 0;
        color: #162238;
        letter-spacing: -.02em;
      }
      .login-gate-card p.login-gate-message {
        color: #65758b;
        margin: 0 0 24px;
        font-size: 15px;
      }
      .login-gate-actions {
        display: flex;
        gap: 11px;
        flex-wrap: wrap;
      }
      .login-gate-card .login-gate-primary,
      .login-gate-card .login-gate-secondary {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 9px;
        padding: 11px 17px;
        font-size: 14px;
        font-weight: 650;
        line-height: 1.4;
        text-decoration: none;
        cursor: pointer;
        font-family: inherit;
      }
      .login-gate-card .login-gate-primary {
        background: #1d4ed8;
        border: 1px solid #1d4ed8;
        color: #fff;
      }
      .login-gate-card .login-gate-primary:hover {
        background: #153eab;
        color: #fff;
      }
      .login-gate-card .login-gate-secondary {
        background: #fff;
        border: 1px solid #cbd5e1;
        color: #34445e;
      }
      .login-gate-card .login-gate-secondary:hover {
        background: #f4f7fb;
        color: #162238;
      }
      .login-gate-card .login-gate-close {
        position: absolute;
        right: 17px;
        top: 14px;
        padding: 5px 9px;
        font-size: 23px;
        line-height: 1;
        border: 0;
        background: transparent;
        color: #64748b;
        cursor: pointer;
      }
      .login-gate-card .login-gate-close:hover { color: #162238; background: transparent; }
      .login-gate-card a:focus-visible,
      .login-gate-card button:focus-visible {
        outline: 3px solid #bfdbfe;
        outline-offset: 3px;
      }
      .login-gate-register {
        margin-top: 18px;
        font-size: 14px;
        color: #65758b;
      }
      .login-gate-register a { color: #1d4ed8; }
      @media (max-width: 520px) {
        .login-gate-card { padding: 22px; }
        .login-gate-actions { flex-direction: column; }
        .login-gate-actions a, .login-gate-actions button { width: 100%; }
      }
    `;

    function showLoginPopup(feature, verificationFailed) {
        if (dialogOpen) return;
        dialogOpen = true;

        if (!document.getElementById("login-gate-style")) {
            const style = document.createElement("style");
            style.id = "login-gate-style";
            style.textContent = popupStyle;
            document.head.appendChild(style);
        }

        const previouslyFocused = document.activeElement;
        const previousOverflow = document.body.style.overflow;
        const backdrop = document.createElement("div");
        backdrop.className = "login-gate-backdrop";
        backdrop.dataset.testid = "login-required-popup";
        backdrop.innerHTML = `
          <div class="login-gate-card" role="dialog" aria-modal="true"
               aria-labelledby="login-gate-title" aria-describedby="login-gate-description">
            <button class="login-gate-close" type="button" aria-label="Close login prompt">×</button>
            <p class="login-gate-eyebrow">Account access</p>
            <h2 id="login-gate-title"></h2>
            <p class="login-gate-message" id="login-gate-description"></p>
            <div class="login-gate-actions">
              <a href="/login.html" class="login-gate-primary" data-testid="login-required-login">Log in to continue</a>
              <button class="login-gate-secondary" type="button" data-testid="login-required-cancel">Not now</button>
            </div>
            <div class="login-gate-register">New to NBA Player Analytics? <a href="/create-account.html">Create an account</a></div>
          </div>`;
        backdrop.querySelector("#login-gate-title").textContent =
            verificationFailed ? "Unable to check access" : "Login required";
        backdrop.querySelector("#login-gate-description").textContent =
            verificationFailed
                ? "We couldn't verify your session right now. Please try again, or log in to your account."
                : `Please log in to access ${feature}. You can still browse player and team statistics without an account.`;

        function close() {
            document.removeEventListener("keydown", onKeydown);
            backdrop.remove();
            document.body.style.overflow = previousOverflow;
            dialogOpen = false;
            if (previouslyFocused && typeof previouslyFocused.focus === "function") {
                previouslyFocused.focus();
            }
        }

        function onKeydown(event) {
            if (event.key === "Escape") {
                event.preventDefault();
                close();
                return;
            }
            if (event.key !== "Tab") return;
            const focusable = [...backdrop.querySelectorAll("a[href], button:not([disabled])")];
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }

        backdrop.querySelector(".login-gate-close").addEventListener("click", close);
        backdrop.querySelector(".login-gate-secondary").addEventListener("click", close);
        backdrop.addEventListener("click", (event) => {
            if (event.target === backdrop) close();
        });
        document.body.appendChild(backdrop);
        document.body.style.overflow = "hidden";
        document.addEventListener("keydown", onKeydown);
        backdrop.querySelector(".login-gate-primary").focus();
    }

    document.addEventListener("click", async (event) => {
        // Preserve standard browser behavior for middle-click, modifiers, and new tabs.
        if (event.defaultPrevented || event.button !== 0 ||
            event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        const target = event.target instanceof Element ? event.target : event.target.parentElement;
        const link = target && target.closest("a[href]");
        if (!link || link.hasAttribute("download") || (link.target && link.target !== "_self")) return;

        let destination;
        try {
            destination = new URL(link.href);
        } catch {
            return;
        }
        if (destination.origin !== window.location.origin) return;
        const feature = restrictedPages.get(destination.pathname.toLowerCase());
        if (!feature) return;

        event.preventDefault();
        if (checkingAccess || dialogOpen) return;
        checkingAccess = true;
        try {
            const response = await fetch("/api/auth/me", {
                method: "GET",
                credentials: "same-origin",
                cache: "no-store",
                headers: { Accept: "application/json" }
            });
            if (response.ok) {
                window.location.assign(destination.href);
            } else if (response.status === 401) {
                showLoginPopup(feature, false);
            } else {
                showLoginPopup(feature, true);
            }
        } catch {
            showLoginPopup(feature, true);
        } finally {
            checkingAccess = false;
        }
    });
})();
