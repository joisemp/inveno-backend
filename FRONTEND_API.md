# Inveno API — Frontend Developer Reference

Complete API reference for integrating the Inveno backend into your React (or any frontend) application.

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

| Tool | URL |
|---|---|
| Swagger UI (try it in browser) | `http://localhost:8000/api/docs/` |
| ReDoc (read-friendly) | `http://localhost:8000/api/redoc/` |
| Raw OpenAPI schema | `http://localhost:8000/api/schema/` |

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

All requests must include:

```http
Content-Type: application/json
```

Authenticated requests must also include:

```http
Authorization: Bearer <access_token>
```

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
  "org_suffix": "acme_west",
  ...
}
```

For super admins: `org_id` and `org_suffix` are `null`.

---

### ~~Register (disabled)~~

`POST /api/auth/register/` is **not available**.  Accounts are created by super
admins through Django Admin.

---

### 1. Set Password — Get-Started Link

Used when a central admin clicks the *Get Started* link in their welcome email.
The link contains `uid` and `token` query parameters.

```
POST /api/auth/password/set/
```

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

**Errors `400`:**
```json
{
  "token": ["Link is invalid or has expired. Request a new welcome email."],
  "new_password2": ["Passwords do not match."]
}
```

> The link expires in **7 days** and is **one-time** — it is invalidated once
> the password is set.

---

### 2. Login

```
POST /api/auth/login/
```

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

**Error `401`:**
```json
{ "detail": "No active account found with the given credentials." }
```

---

### 3. Refresh Access Token

Access tokens expire in **15 minutes**. Use the refresh token to get a new one.

```
POST /api/auth/token/refresh/
```

**Request body:**
```json
{ "refresh": "<refresh_token>" }
```

**Success `200`:**
```json
{ "access": "new_access_token...", "refresh": "new_refresh_token..." }
```

> Note: `ROTATE_REFRESH_TOKENS = True` — each refresh call returns a **new refresh token**. Store the new one.

**Error `401`:**
```json
{ "detail": "Token is invalid or expired.", "code": "token_not_valid" }
```

---

### 4. Verify Token

```
POST /api/auth/token/verify/
```

```json
{ "token": "<access_token>" }
```

**Success `200`:** `{}`  
**Error `401`:** Token is invalid or expired.

---

### 5. Logout

Blacklists the refresh token so it can't be used again.

```
POST /api/auth/logout/
Authorization: Bearer <access_token>
```

**Request body:**
```json
{ "refresh": "<refresh_token>" }
```

**Success `200`:**
```json
{ "detail": "Successfully logged out." }
```

---

## User Profile

### Get My Profile

```
GET /api/auth/me/
Authorization: Bearer <access_token>
```

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

---

### Update My Profile

```
PATCH /api/auth/me/
Authorization: Bearer <access_token>
```

**Request body (any subset of profile fields):**
```json
{
  "first_name": "Jane",
  "last_name": "Smith",
  "phone": "+919876543210"
}
```

> `email`, `org`, and `user_type` are read-only and cannot be changed via this endpoint.

**Success `200`:** Returns updated object with the new profile values reflected in `profile`.

---

## Password Management

### Change Password (authenticated)

```
POST /api/auth/password/change/
Authorization: Bearer <access_token>
```

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

**Error `400`:**
```json
{ "old_password": ["Old password is incorrect."] }
```

---

### Forgot Password — Request Reset Link

```
POST /api/auth/password/reset/
```

```json
{ "email": "user@example.com" }
```

**Success `200`** (always, even if email doesn't exist — prevents enumeration):
```json
{ "detail": "If an account with that email exists, a reset link has been sent." }
```

> In **development**, the email is printed to the Docker terminal — check `docker compose logs api`.

---

### Forgot Password — Confirm Reset

```
POST /api/auth/password/reset/confirm/
```

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

**Error `400`:**
```json
{ "token": ["Reset link is invalid or has expired."] }
```

---

## System

### Health Check

```
GET /api/health/
```

No authentication required.

**Success `200`:**
```json
{ "status": "ok", "db": "ok", "redis": "ok" }
```

**Degraded `503`:**
```json
{ "status": "degraded", "db": "ok", "redis": "error" }
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

The API enforces rate limits. When exceeded, you receive:

**`429 Too Many Requests`**
```json
{ "detail": "Request was throttled. Expected available in 42 seconds." }
```

| Limit | Rate |
|---|---|
| Unauthenticated | 100 requests / day |
| Authenticated | 1000 requests / day |
| Auth endpoints (login, register, reset) | 10 requests / min |

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
| `httpOnly` cookie | ✅ Best | Safe from XSS. Requires cookie-based auth setup. |
| In-memory (React state) | ✅ Good | Lost on refresh — pair with silent refresh strategy. |
| `localStorage` | ⚠️ Risky | Vulnerable to XSS. Avoid for access tokens. |

### Recommended pattern (in-memory + refresh cookie)

1. Store `access` token in memory (React context / Zustand / Redux)
2. Store `refresh` token in an `httpOnly` cookie (set by the server or a BFF)
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
        const { data } = await axios.post(`${import.meta.env.VITE_API_URL}/api/auth/token/refresh/`, { refresh });
        setAccessToken(data.access);   // store new access token
        setRefreshToken(data.refresh); // store new refresh token (rotation)
        original.headers.Authorization = `Bearer ${data.access}`;
        return api(original);
      } catch {
        clearTokens(); // logout
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;
```

### Register

```js
const register = async (email, password, password2, firstName, lastName) => {
  const { data } = await api.post('/api/auth/register/', {
    email,
    password,
    password2,
    first_name: firstName,
    last_name: lastName,
  });
  return data; // { detail: "Account created successfully." }
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
  return data; // { id, email, first_name, last_name, full_name, date_joined }
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
  // Always resolves — check email for the reset link
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

You will see the full email body including the password reset link.

---

## Changelog

| Version | Date | Notes |
|---|---|---|
| 1.0.0 | 2026-09-08 | Initial release |
