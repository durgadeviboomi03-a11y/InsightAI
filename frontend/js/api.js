/**
 * frontend/js/api.js
 *
 * Centralized API client for InsightAI's FastAPI backend.
 *
 * Every function every page's inline script has been waiting on
 * (guarded with `typeof xyz !== 'function'` checks) is defined here.
 */

const API_BASE_URL = 'http://localhost:8000/api';
const TOKEN_KEY = 'insightai_access_token';
const REFRESH_TOKEN_KEY = 'insightai_refresh_token';

// =========================================================
// ---------------------- Core Request Helper ----------------------
// =========================================================

/**
 * Builds the standard headers for a request, attaching the JWT
 * Authorization header if a token is present.
 *
 * @param {boolean} isFormData - if true, skips setting Content-Type
 *   (the browser sets the correct multipart boundary automatically
 *   for FormData uploads).
 */
function _buildHeaders(isFormData = false) {
    const headers = {};
    if (!isFormData) {
        headers['Content-Type'] = 'application/json';
    }
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
}

/**
 * Attempts to silently refresh the access token using the stored
 * refresh token. Returns true if successful, false otherwise.
 */
async function _tryRefreshToken() {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (!refreshToken) return false;

    try {
        const response = await fetch(
            `${API_BASE_URL}/auth/refresh?refresh_token=${encodeURIComponent(refreshToken)}`,
            { method: 'POST' }
        );
        if (!response.ok) return false;

        const tokens = await response.json();
        localStorage.setItem(TOKEN_KEY, tokens.access_token);
        localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
        return true;
    } catch {
        return false;
    }
}

/**
 * Core request function used by every API call in this file.
 *
 * Handles:
 * - Building the full URL and headers
 * - JSON-encoding the body (unless it's FormData)
 * - Parsing JSON responses and throwing readable Error objects on failure
 * - Automatically retrying once after a silent token refresh on a 401
 *
 * @param {string} path - API path, e.g. '/auth/login'
 * @param {object} options - { method, body, isFormData }
 * @param {boolean} _isRetry - internal flag to prevent infinite refresh loops
 */
async function _request(path, options = {}, _isRetry = false) {
    const { method = 'GET', body = null, isFormData = false } = options;

    const fetchOptions = {
        method,
        headers: _buildHeaders(isFormData),
    };

    if (body !== null) {
        fetchOptions.body = isFormData ? body : JSON.stringify(body);
    }

    let response;
    try {
        response = await fetch(`${API_BASE_URL}${path}`, fetchOptions);
    } catch (networkError) {
        throw new Error('Could not reach the server. Please check your connection and try again.');
    }

    // ---------- Handle expired token with a single silent retry ----------
    if (response.status === 401 && !_isRetry) {
        const refreshed = await _tryRefreshToken();
        if (refreshed) {
            return _request(path, options, true);
        }
        // Refresh failed too — force a clean re-login.
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_TOKEN_KEY);
        window.location.href = 'login.html';
        throw new Error('Your session has expired. Please log in again.');
    }

    // ---------- Handle file downloads (non-JSON responses) ----------
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
        if (!response.ok) {
            throw new Error(`Request failed with status ${response.status}.`);
        }
        return response; // Caller handles the raw response (e.g. file download).
    }

    const data = await response.json();

    if (!response.ok) {
        const detail = data.detail;
        const message = Array.isArray(detail)
            ? detail.map((d) => d.msg).join(', ')
            : (detail || 'Something went wrong. Please try again.');
        throw new Error(message);
    }

    return data;
}

// =========================================================
// ------------------------ Auth ------------------------
// =========================================================

async function registerUser(fullName, email, password) {
    return _request('/auth/register', {
        method: 'POST',
        body: { full_name: fullName, email, password },
    });
}

async function loginUser(email, password) {
    const tokens = await _request('/auth/login', {
        method: 'POST',
        body: { email, password },
    });
    return tokens; // Caller (login.html) stores tokens in localStorage.
}

async function getCurrentUser() {
    return _request('/auth/me', { method: 'GET' });
}

// =========================================================
// ---------------------- User Profile ----------------------
// =========================================================

async function updateProfile({ full_name, email }) {
    const body = {};
    if (full_name !== undefined) body.full_name = full_name;
    if (email !== undefined) body.email = email;
    return _request('/users/me', { method: 'PATCH', body });
}

async function listAllUsers() {
    return _request('/users', { method: 'GET' });
}

async function deactivateUser(publicId) {
    return _request(`/users/${publicId}/deactivate`, { method: 'PATCH' });
}

// =========================================================
// --------------------- Datasets ---------------------
// =========================================================

async function listDatasets() {
    return _request('/datasets', { method: 'GET' });
}

async function getDataset(publicId) {
    return _request(`/datasets/${publicId}`, { method: 'GET' });
}

async function getDatasetOverview(publicId) {
    return _request(`/datasets/${publicId}/overview`, { method: 'GET' });
}

async function uploadDataset(file) {
    const formData = new FormData();
    formData.append('file', file);
    return _request('/datasets', {
        method: 'POST',
        body: formData,
        isFormData: true,
    });
}

async function deleteDataset(publicId) {
    return _request(`/datasets/${publicId}`, { method: 'DELETE' });
}

// =========================================================
// ------------------- AI Chat / NL→SQL -------------------
// =========================================================

async function sendChatMessage(datasetPublicId, message) {
    return _request('/chat/message', {
        method: 'POST',
        body: { dataset_public_id: datasetPublicId, message },
    });
}

async function getChatHistory(datasetPublicId) {
    return _request(`/chat/history/${datasetPublicId}`, { method: 'GET' });
}

async function runNLQuery(datasetPublicId, question) {
    return _request('/chat/nl-query', {
        method: 'POST',
        body: { dataset_public_id: datasetPublicId, question },
    });
}

// =========================================================
// ---------------------- Reports ----------------------
// =========================================================

async function createReport(datasetPublicId, title, format) {
    return _request('/reports', {
        method: 'POST',
        body: { dataset_public_id: datasetPublicId, title, format },
    });
}

async function listReports() {
    return _request('/reports', { method: 'GET' });
}

async function deleteReport(publicId) {
    return _request(`/reports/${publicId}`, { method: 'DELETE' });
}

/**
 * Triggers a browser download of a generated report.
 *
 * Unlike other calls, the download endpoint returns a raw file, not JSON —
 * so this fetches it as a blob and creates a temporary link to trigger
 * the browser's native "Save As" behavior, rather than returning parsed data.
 */
async function downloadReport(publicId) {
    const token = localStorage.getItem(TOKEN_KEY);
    const response = await fetch(`${API_BASE_URL}/reports/${publicId}/download`, {
        headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
        throw new Error('Could not download the report.');
    }

    const disposition = response.headers.get('content-disposition') || '';
    const filenameMatch = disposition.match(/filename="?([^"]+)"?/);
    const filename = filenameMatch ? filenameMatch[1] : 'report';

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
}

// =========================================================
// --------------------- Forecasting ---------------------
// =========================================================

async function createForecast(datasetPublicId, dateColumn, valueColumn, periodsAhead) {
    return _request('/forecast', {
        method: 'POST',
        body: {
            dataset_public_id: datasetPublicId,
            date_column: dateColumn,
            value_column: valueColumn,
            periods_ahead: periodsAhead,
        },
    });
}

// =========================================================
// ------------------------ Admin ------------------------
// =========================================================

async function getAdminStats() {
    return _request('/admin/stats', { method: 'GET' });
}

async function listAllDatasetsAdmin() {
    return _request('/admin/datasets', { method: 'GET' });
}

async function listAllReportsAdmin() {
    return _request('/admin/reports', { method: 'GET' });
}