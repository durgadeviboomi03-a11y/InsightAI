/**
 * frontend/js/app.js
 *
 * Shared application JavaScript, loaded on every authenticated page.
 *
 * Responsibilities:
 * - requireAuth(): centralized auth guard, replacing the inline IIFE
 *   duplicated across every page so far.
 * - Shared logout handling.
 * - Common formatting helpers (dates, file sizes).
 * - A lightweight toast notification system.
 */

const TOKEN_KEY = 'insightai_access_token';
const REFRESH_TOKEN_KEY = 'insightai_refresh_token';

/**
 * Redirects to login.html immediately if no access token is present.
 *
 * This replaces the inline IIFE auth-guard block that was duplicated at
 * the top of every page's <script> section (dashboard.html, upload.html,
 * charts.html, etc.). Those inline blocks still work fine — this function
 * exists so future pages (and a future cleanup pass on existing ones) can
 * call one shared implementation instead of copy-pasting it.
 *
 * @returns {string|null} The access token, if present.
 */
function requireAuth() {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
        window.location.href = 'login.html';
        return null;
    }
    return token;
}

/**
 * Clears stored tokens and redirects to the login page.
 * Shared by every page's logout button/link.
 */
function logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    window.location.href = 'login.html';
}

/**
 * Wires up any element with id="logoutBtn" (and, if present,
 * id="settingsLogoutBtn") to call logout() on click.
 *
 * Called automatically on DOMContentLoaded below, so individual pages
 * don't need to attach this listener themselves.
 */
function attachLogoutHandlers() {
    const logoutIds = ['logoutBtn', 'settingsLogoutBtn'];
    logoutIds.forEach((id) => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('click', function (event) {
                event.preventDefault();
                logout();
            });
        }
    });
}

/**
 * Formats an ISO date string into a short, readable date
 * (e.g. "Jul 21, 2026").
 *
 * @param {string} isoString
 * @returns {string}
 */
function formatDate(isoString) {
    if (!isoString) return '—';
    const date = new Date(isoString);
    return date.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
}

/**
 * Formats an ISO date string into a readable date + time
 * (e.g. "Jul 21, 2026, 3:45 PM").
 *
 * @param {string} isoString
 * @returns {string}
 */
function formatDateTime(isoString) {
    if (!isoString) return '—';
    const date = new Date(isoString);
    return date.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
    });
}

/**
 * Formats a byte count into a human-readable size string.
 *
 * @param {number} bytes
 * @returns {string}
 */
function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Escapes HTML special characters in a string, preventing it from being
 * interpreted as markup when inserted via innerHTML. Use this for any
 * user-supplied or AI-generated text before rendering it.
 *
 * @param {string} text
 * @returns {string}
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Shows a temporary toast notification in the bottom-right corner of the
 * screen. Creates the toast container on first use if it doesn't exist yet.
 *
 * @param {string} message
 * @param {'success'|'danger'|'warning'|'info'} type
 * @param {number} durationMs How long before the toast auto-dismisses.
 */
function showToast(message, type = 'info', durationMs = 4000) {
    let container = document.getElementById('insightaiToastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'insightaiToastContainer';
        container.style.position = 'fixed';
        container.style.bottom = '1.5rem';
        container.style.right = '1.5rem';
        container.style.zIndex = '2000';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.gap = '0.5rem';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `alert alert-${type} shadow-sm mb-0`;
    toast.style.minWidth = '260px';
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.transition = 'opacity 0.3s ease';
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, durationMs);
}

// ---------- Auto-run on every page load ----------
document.addEventListener('DOMContentLoaded', function () {
    attachLogoutHandlers();
});