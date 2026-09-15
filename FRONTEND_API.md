# Inveno API — Frontend Developer Reference

Complete API reference for integrating the Inveno backend into your React (or any frontend) application.

Each endpoint documents **request**, **success** (status + JSON), and **errors** (status + JSON) as returned by the API.

---

## Base URL

| Environment | URL |
|---|---|
| Local dev (Docker) | `http://localhost:8000` |
| Production | `https://your-railway-domain.up.railway.app` |

Set this as an environment variable in your React project:

```env
# Vite
VITE_API_URL=http://localhost:8000

# Create React App
REACT_APP_API_URL=http://localhost:8000
```

---

## Interactive Docs

| Tool | URL | Access |
|---|---|---|
| Swagger UI | `http://localhost:8000/api/docs/` | Superuser only (log in at `/admin/` first) |
| Frontend guide (React + Vite + TS) | `http://localhost:8000/api/docs/frontend/` | Superuser only |
| ReDoc | `http://localhost:8000/api/redoc/` | Superuser only |
| Raw OpenAPI schema | `http://localhost:8000/api/schema/` | Superuser only |

---

## Quick Start for Frontend Devs

You don't need to clone or run the backend code. Just use the pre-built Docker image:

```bash
# 1. Copy the frontend compose file into your React project root
cp path/to/inveno-api/docker-compose.frontend-dev.yml .

# 2. Copy the env example and fill it in
cp path/to/inveno-api/.env.frontend.example .env.api

# 3. Start the API
docker compose -f docker-compose.frontend-dev.yml up

# API is now running at http://localhost:8000
```

---

## Request Headers

All JSON requests must include:

```http
Content-Type: application/json
```

Authenticated requests must also include:

```http
Authorization: Bearer <access_token>
```

---

## Shared Error Responses

These appear on many endpoints. Individual sections reference them by name.

### `401` — Not authenticated

```json
{ "detail": "Authentication credentials were not provided." }
```

### `401` — Invalid or expired JWT

```json
{
  "detail": "Given token not valid for any token type",
  "code": "token_not_valid",
  "messages": [
    {
      "token_class": "AccessToken",
      "token_type": "access",
      "message": "Token is invalid or expired"
    }
  ]
}
```

### `429` — Rate limited

```json
{ "detail": "Request was throttled. Expected available in 42 seconds." }
```

Auth endpoints (login, password set/reset) are limited to **10 requests / minute**.

---

## Authentication Flow

### Overview

> **Account creation is admin-only.**  
> A super admin registers organisations (and their first central admin) through
> the Django Admin at `/admin/`.  The central admin receives a welcome email
> with a *Get Started* link.  They click the link, set their password at
> `POST /api/auth/password/set/`, then log in normally.

```
[Super admin] creates org + central admin in /admin/
  → Welcome email sent to central admin
  → Central admin clicks "Get Started" link
  → POST /api/auth/password/set/  (uid + token from URL + new_password)
  → POST /api/auth/login/         (email + password)
  → receive { access, refresh }
Use access token for API calls (expires in 15 min)
Use refresh token to get a new access token (expires in 7 days)
On logout → POST /api/auth/logout/ with the refresh token
```

### JWT Token Claims

The access token payload includes:

```json
{
  "user_id": "uuid",
  "user_type": "central_admin",
  "org_id": "uuid-of-org",
  "org_suffix": "acme_west"
}
```

For super admins: `org_id` and `org_suffix` are `null`.

---

### ~~Register (disabled)~~

`POST /api/auth/register/` is **not available**. Accounts are created by super
admins through Django Admin.

---

### 1. Set Password — Get-Started Link

Used when a central admin clicks the *Get Started* link in their welcome email.
The link contains `uid` and `token` query parameters.

| | |
|---|---|
| **Method / URL** | `POST /api/auth/password/set/` |
| **Auth** | None |

**Request body:**
```json
{
  "uid": "<uid from URL>",
  "token": "<token from URL>",
  "new_password": "StrongPass123!",
  "new_password2": "StrongPass123!"
}
```

**Success `200`:**
```json
{ "detail": "Password set successfully. You can now log in." }
```

**Error `400` — invalid uid:**
```json
{ "uid": ["Invalid link."] }
```

**Error `400` — invalid / expired / already-used token:**
```json
{ "token": ["Link is invalid or has expired. Request a new welcome email."] }
```

**Error `400` — password mismatch:**
```json
{ "new_password2": ["Passwords do not match."] }
```

**Error `400` — weak password:**
```json
{ "new_password": ["This password is too common."] }
```

**Error `429`:** see [Shared Error Responses](#429--rate-limited)

> The link expires in **7 days** and is **one-time** — it is invalidated once the password is set.

---

### 2. Login

| | |
|---|---|
| **Method / URL** | `POST /api/auth/login/` |
| **Auth** | None |

**Request body:**
```json
{
  "email": "user@example.com",
  "password": "StrongPass123!"
}
```

**Success `200`:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGci...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGci..."
}
```

**Error `401` — wrong email or password:**
```json
{ "detail": "No active account found with the given credentials." }
```

**Error `400` — organisation suspended:**
```json
{
  "non_field_errors": [
    "Your organisation has been suspended. Please contact your administrator."
  ]
}
```

**Error `400` — missing fields:**
```json
{
  "email": ["This field is required."],
  "password": ["This field is required."]
}
```

**Error `429`:** see [Shared Error Responses](#429--rate-limited)

---

### 3. Refresh Access Token

Access tokens expire in **15 minutes**. Use the refresh token to get a new one.

| | |
|---|---|
| **Method / URL** | `POST /api/auth/token/refresh/` |
| **Auth** | None (body carries refresh token) |

**Request body:**
```json
{ "refresh": "<refresh_token>" }
```

**Success `200`:**
```json
{
  "access": "new_access_token...",
  "refresh": "new_refresh_token..."
}
```

> `ROTATE_REFRESH_TOKENS = True` — each refresh returns a **new refresh token**. Store it. The old refresh token is blacklisted.

**Error `400` — missing refresh:**
```json
{ "refresh": ["This field is required."] }
```

**Error `401` — invalid, expired, or blacklisted refresh:**
```json
{
  "detail": "Token is invalid or expired",
  "code": "token_not_valid"
}
```

---

### 4. Verify Token

| | |
|---|---|
| **Method / URL** | `POST /api/auth/token/verify/` |
| **Auth** | None |

**Request body:**
```json
{ "token": "<access_token>" }
```

**Success `200`:**
```json
{}
```

**Error `400` — missing token:**
```json
{ "token": ["This field is required."] }
```

**Error `401` — invalid or expired token:**
```json
{
  "detail": "Token is invalid or expired",
  "code": "token_not_valid"
}
```

---

### 5. Logout

Blacklists the refresh token so it cannot be used again.

| | |
|---|---|
| **Method / URL** | `POST /api/auth/logout/` |
| **Auth** | Bearer access token required |

**Request body:**
```json
{ "refresh": "<refresh_token>" }
```

**Success `200`:**
```json
{ "detail": "Successfully logged out." }
```

**Error `400` — missing refresh:**
```json
{ "detail": "Refresh token is required." }
```

**Error `400` — invalid or already blacklisted:**
```json
{ "detail": "Invalid or already blacklisted token." }
```

**Error `401`:** see [Shared Error Responses](#401--not-authenticated)

---

## User Profile

### Get My Profile

| | |
|---|---|
| **Method / URL** | `GET /api/auth/me/` |
| **Auth** | Bearer access token required |

**Success `200`:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "date_joined": "2026-09-08T12:00:00Z",
  "updated_at": "2026-09-08T12:00:00Z",
  "profile": {
    "user_type": "central_admin",
    "first_name": "Jane",
    "last_name": "Doe",
    "phone": "+1234567890",
    "full_name": "Jane Doe"
  },
  "org": {
    "id": "org-uuid",
    "name": "Acme Corp",
    "org_suffix": "acme_west",
    "location": "New York",
    "is_active": true,
    "registered_on": "2026-09-01T10:00:00Z"
  }
}
```

> For super admins `org` is `null`.

**Error `401`:** see [Shared Error Responses](#401--not-authenticated)

---

### Update My Profile

| | |
|---|---|
| **Method / URL** | `PATCH /api/auth/me/` |
| **Auth** | Bearer access token required |

**Request body (any subset):**
```json
{
  "first_name": "Jane",
  "last_name": "Smith",
  "phone": "+919876543210"
}
```

> `email`, `org`, and `user_type` are read-only.

**Success `200`:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "date_joined": "2026-09-08T12:00:00Z",
  "updated_at": "2026-09-09T08:15:00Z",
  "profile": {
    "user_type": "central_admin",
    "first_name": "Jane",
    "last_name": "Smith",
    "phone": "+919876543210",
    "full_name": "Jane Smith"
  },
  "org": {
    "id": "org-uuid",
    "name": "Acme Corp",
    "org_suffix": "acme_west",
    "location": "New York",
    "is_active": true,
    "registered_on": "2026-09-01T10:00:00Z"
  }
}
```

**Error `400` — validation:**
```json
{ "phone": ["Ensure this field has no more than 30 characters."] }
```

**Error `401`:** see [Shared Error Responses](#401--not-authenticated)

---

## Password Management

### Change Password (authenticated)

| | |
|---|---|
| **Method / URL** | `POST /api/auth/password/change/` |
| **Auth** | Bearer access token required |

**Request body:**
```json
{
  "old_password": "OldPass123!",
  "new_password": "NewPass456!",
  "new_password2": "NewPass456!"
}
```

**Success `200`:**
```json
{ "detail": "Password updated successfully." }
```

**Error `400` — wrong old password:**
```json
{ "old_password": ["Old password is incorrect."] }
```

**Error `400` — password mismatch:**
```json
{ "new_password2": ["Passwords do not match."] }
```

**Error `400` — weak new password:**
```json
{ "new_password": ["This password is too common."] }
```

**Error `401`:** see [Shared Error Responses](#401--not-authenticated)

---

### Forgot Password — Request Reset Link

| | |
|---|---|
| **Method / URL** | `POST /api/auth/password/reset/` |
| **Auth** | None |

**Request body:**
```json
{ "email": "user@example.com" }
```

**Success `200`** (always, even if the email does not exist — prevents enumeration):
```json
{ "detail": "If an account with that email exists, a reset link has been sent." }
```

**Error `400` — invalid email format:**
```json
{ "email": ["Enter a valid email address."] }
```

**Error `429`:** see [Shared Error Responses](#429--rate-limited)

> In **development**, the email is printed to the Docker terminal — check `docker compose logs api`.

---

### Forgot Password — Confirm Reset

| | |
|---|---|
| **Method / URL** | `POST /api/auth/password/reset/confirm/` |
| **Auth** | None |

**Request body:**
```json
{
  "uid": "<uid from email link>",
  "token": "<token from email link>",
  "new_password": "NewPass789!",
  "new_password2": "NewPass789!"
}
```

**Success `200`:**
```json
{ "detail": "Password has been reset successfully." }
```

**Error `400` — invalid uid:**
```json
{ "uid": ["Invalid reset link."] }
```

**Error `400` — invalid or expired token:**
```json
{ "token": ["Reset link is invalid or has expired."] }
```

**Error `400` — password mismatch:**
```json
{ "new_password2": ["Passwords do not match."] }
```

**Error `400` — weak password:**
```json
{ "new_password": ["This password is too common."] }
```

**Error `429`:** see [Shared Error Responses](#429--rate-limited)

---

## System

### Health Check

| | |
|---|---|
| **Method / URL** | `GET /api/health/` |
| **Auth** | None |

**Success `200`:**
```json
{ "status": "ok", "db": "ok", "redis": "ok" }
```

**Degraded `503`:**
```json
{ "status": "degraded", "db": "ok", "redis": "error" }
```

---

### API Documentation (superuser only)

These endpoints require a Django session from an `is_staff` user (log in at `/admin/` first). Regular JWT users cannot access them.

| Method / URL | Success | Error |
|---|---|---|
| `GET /api/docs/` | `200` — Swagger UI HTML | `403` (below) |
| `GET /api/docs/frontend/` | `200` — Frontend guide HTML | `403` (below) |
| `GET /api/redoc/` | `200` — ReDoc HTML | `403` (below) |
| `GET /api/schema/` | `200` — OpenAPI JSON/YAML | `403` (below) |

**Error `403`:**
```json
{ "detail": "You do not have permission to perform this action." }
```

**Error `401`** (no session and no credentials):
```json
{ "detail": "Authentication credentials were not provided." }
```

---

## Error Response Format

### Field validation errors
```json
{
  "email": ["Enter a valid email address."],
  "password": ["This password is too short."]
}
```

### Non-field errors
```json
{ "detail": "Authentication credentials were not provided." }
```

### Common HTTP status codes

| Code | Meaning |
|---|---|
| `200` | Success |
| `201` | Created |
| `400` | Validation error |
| `401` | Not authenticated or token expired |
| `403` | Authenticated but forbidden |
| `404` | Not found |
| `429` | Rate limit exceeded |
| `500` | Server error |
| `503` | Service unavailable |

---

## Rate Limiting

| Limit | Rate |
|---|---|
| Unauthenticated | 100 requests / day |
| Authenticated | 1000 requests / day |
| Auth endpoints (login, password set/reset) | 10 requests / min |

**Handling 429 in your app:**

```js
if (response.status === 429) {
  const retryAfter = response.headers.get('Retry-After'); // seconds
  // Show the user a "too many requests" message
}
```

---

## Pagination

List endpoints return paginated results:

```json
{
  "count": 100,
  "next": "http://localhost:8000/api/some-list/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

Default page size: **20**. Use `?page=2` to navigate.

---

## CORS

The API allows requests from these origins by default:

- `http://localhost:3000` (Create React App)
- `http://localhost:5173` (Vite)

In production, configure `CORS_ALLOWED_ORIGINS` on the server to include your deployed frontend URL.

---

## Token Storage Recommendations

| Method | Security | Notes |
|---|---|---|
| `httpOnly` cookie | Best | Safe from XSS. Requires cookie-based auth setup. |
| In-memory (React state) | Good | Lost on refresh — pair with silent refresh strategy. |
| `localStorage` | Risky | Vulnerable to XSS. Avoid for access tokens. |

### Recommended pattern (in-memory + refresh)

1. Store `access` token in memory (React context / Zustand / Redux)
2. Store `refresh` token securely (prefer httpOnly cookie via BFF, or memory)
3. On page load, call `POST /api/auth/token/refresh/` to get a new access token silently

---

## Code Examples

### Axios setup (recommended)

```js
// src/lib/api.js
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Attach access token to every request
api.interceptors.request.use((config) => {
  const token = getAccessToken(); // your token getter
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auto-refresh on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      try {
        const refresh = getRefreshToken();
        const { data } = await axios.post(
          `${import.meta.env.VITE_API_URL}/api/auth/token/refresh/`,
          { refresh }
        );
        setAccessToken(data.access);
        setRefreshToken(data.refresh); // rotation — store the new refresh
        original.headers.Authorization = `Bearer ${data.access}`;
        return api(original);
      } catch {
        clearTokens();
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;
```

### Set password (welcome email / Get Started)

```js
const setPassword = async (uid, token, newPassword, newPassword2) => {
  const { data } = await api.post('/api/auth/password/set/', {
    uid,
    token,
    new_password: newPassword,
    new_password2: newPassword2,
  });
  return data; // { detail: "Password set successfully. You can now log in." }
};
```

### Login

```js
const login = async (email, password) => {
  const { data } = await api.post('/api/auth/login/', { email, password });
  setAccessToken(data.access);
  setRefreshToken(data.refresh);
  return data;
};
```

### Get profile

```js
const getProfile = async () => {
  const { data } = await api.get('/api/auth/me/');
  // { id, email, date_joined, updated_at, profile: {...}, org: {...} | null }
  return data;
};
```

### Logout

```js
const logout = async () => {
  await api.post('/api/auth/logout/', { refresh: getRefreshToken() });
  clearTokens();
};
```

### Forgot password

```js
const forgotPassword = async (email) => {
  await api.post('/api/auth/password/reset/', { email });
  // Always resolves with 200 — check email for the reset link
};
```

### Reset password

```js
const resetPassword = async (uid, token, newPassword, newPassword2) => {
  await api.post('/api/auth/password/reset/confirm/', {
    uid,
    token,
    new_password: newPassword,
    new_password2: newPassword2,
  });
};
```

---

## Development Email

In development, emails are **not sent** — they are printed to the API Docker container logs.

To see them:

```bash
docker compose logs api
# or watch live
docker compose logs -f api
```

You will see the full email body including the password reset or Get Started link.

---

## Changelog

| Version | Date | Notes |
|---|---|---|
| 1.0.0 | 2026-09-08 | Initial release |
| 1.1.0 | 2026-09-14 | Full success/error payloads per endpoint; register removed |
