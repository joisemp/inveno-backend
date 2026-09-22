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

# 3. Start the API attached (not -d) so you can type k/w if demo data exists
docker compose -f docker-compose.frontend-dev.yml up

# API is now running at http://localhost:8000
```

Demo logins (password for all: `DemoPass123!`):

| Login (email) | Role |
|---|---|
| `super@inveno.local` | super_admin (Swagger / Django Admin) |
| `admin@demo.inveno.local` | central_admin |
| `ops@demo.inveno.local` | operation_incharge |
| `warehouse@demo.inveno.local` | warehouse_manager |
| `space@demo.inveno.local` | space_incharge (North Wing) |

Set `SEED_DEMO=false` in `.env.api` to skip seeding. Use attached `docker compose up` (not `-d`) so **k** keep / **w** wipe can be typed. `-d` keeps existing rows. To wipe without the prompt:

```bash
docker compose -f docker-compose.frontend-dev.yml exec -it api python manage.py seed_demo --reset
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

## Identifiers

Public JSON and URLs use **`slug` only** — never UUID `id` (the login User on
`/api/auth/me/` is the existing exception). Slugs are generated. The first
value is `slugify(name)`. If that is taken, the next is
`{base}-{YYYYMMDD}-{letter}` using the server's local **date** (no time):
`jane-doe`, then `jane-doe-20260922-a`, then `-b`, then `-aa`. Existing slugs
are not rewritten.

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

> **Account creation is admin-driven.**  
> A super admin registers organisations (and their first central admin) through
> the Django Admin at `/admin/`.  After that, a **central admin** can add more
> users to their organisation via `POST /api/orgs/members/` (`central_admin` or
> `warehouse_manager`).  Each new user receives a welcome email with a
> *Get Started* link.  They click the link, set their password at
> `POST /api/auth/password/set/`, then log in normally.

```
[Super admin] creates org + first central admin in /admin/
  — or —
[Central admin] POST /api/orgs/members/  (email, names, user_type)
  → Welcome email sent
  → User clicks "Get Started" link
  → POST /api/auth/password/set/  (uid + token from URL + new_password)
  → POST /api/auth/login/         (email + password, withCredentials: true)
  → receive { access } + httpOnly refresh cookie (inveno_refresh)
Store access in memory; send Authorization: Bearer on API calls (15 min)
Silent refresh → POST /api/auth/token/refresh/ (cookie only, withCredentials)
On logout → POST /api/auth/logout/ (withCredentials) clears the cookie
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

`POST /api/auth/register/` is **not available**. The first central admin is
created by a super admin in Django Admin. Further org users are added by a
central admin at `POST /api/orgs/members/`.

---

### 1. Set Password — Get-Started Link

Used when a new org user clicks the *Get Started* link in their welcome email.
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

**Success `200` — JSON body:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGci..."
}
```

**Success `200` — response headers (Set-Cookie):**
```http
Set-Cookie: inveno_refresh=<refresh_token>; HttpOnly; Path=/api/auth/; SameSite=Lax; Max-Age=604800
```

> The refresh token is **never** in the JSON body. The browser stores it automatically when `withCredentials: true`.

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

**Error `400` — account suspended:**
```json
{
  "non_field_errors": [
    "Your account has been suspended. Please contact your administrator."
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

Access tokens expire in **15 minutes**. Call refresh with the httpOnly cookie (no JSON body).

| | |
|---|---|
| **Method / URL** | `POST /api/auth/token/refresh/` |
| **Auth** | None — refresh httpOnly cookie required |
| **Credentials** | `withCredentials: true` (axios) or `credentials: 'include'` (fetch) |

**Request body:** empty `{}` or omit entirely.

**Success `200` — JSON body:**
```json
{
  "access": "new_access_token..."
}
```

**Success `200` — response headers:** new `Set-Cookie: inveno_refresh=...` (rotated).

> `ROTATE_REFRESH_TOKENS = True` — each refresh rotates the cookie. The old refresh token is blacklisted.

**Error `401` — missing cookie:**
```json
{
  "detail": "Refresh cookie is missing.",
  "code": "token_not_valid"
}
```

**Error `401` — invalid, expired, or blacklisted refresh:**
```json
{
  "detail": "Token is invalid or expired",
  "code": "token_not_valid"
}
```

**Error `429`:** see [Shared Error Responses](#429--rate-limited)

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

Blacklists the refresh cookie and clears it from the browser.

| | |
|---|---|
| **Method / URL** | `POST /api/auth/logout/` |
| **Auth** | None — refresh httpOnly cookie required |
| **Credentials** | `withCredentials: true` |

**Request body:** empty `{}` or omit entirely.

**Success `200`:**
```json
{ "detail": "Successfully logged out." }
```

The response clears the `inveno_refresh` cookie. Bearer access is **not** required (works with an expired access token).

**Error `429`:** see [Shared Error Responses](#429--rate-limited)

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
        "full_name": "Jane Doe",
        "space": null
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

> For super admins `org` is `null`. For space incharges, `profile.space` is
> `{ "slug": "...", "name": "..." }` when assigned, otherwise `null`.

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
        "full_name": "Jane Smith",
        "space": null
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

## Organisation Members

Central admins manage users in **their own organisation**. The org is taken
from the JWT; there is no `org_id` in the URL or body.

Public identifier is **`slug`** (auto-generated from the member's name). UUID
`id` is not returned.

Assignable `user_type` values: `central_admin`, `operation_incharge`,
`warehouse_manager`, `space_incharge`. `super_admin` cannot be created here.
Do **not** send `space` on create — assign space incharges with
`POST /api/orgs/spaces/{slug}/incharges/`.

Operation incharges, warehouse managers, space incharges, and super admins
receive `403` on these endpoints.

### List Members

| | |
|---|---|
| **Method / URL** | `GET /api/orgs/members/` |
| **Auth** | Bearer access token — **central admin** of an active org |

Paginated (`count` / `next` / `previous` / `results`, page size 20).

Optional query: `status=active` or `status=suspended`. Omit `status` to return
every member. `is_active` on each item is `false` when the user is suspended.

**Error `400` — invalid status:**
```json
{ "status": ["Must be \"active\" or \"suspended\"."] }
```

**Success `200`:**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "slug": "alice-smith",
      "email": "alice@acme.com",
      "user_type": "warehouse_manager",
      "first_name": "Alice",
      "last_name": "Smith",
      "phone": "+15551234",
      "full_name": "Alice Smith",
      "is_active": true,
      "has_usable_password": false,
      "date_joined": "2026-09-15T10:00:00Z",
      "space": null
    }
  ]
}
```

**Error `401`:** see [Shared Error Responses](#401--not-authenticated)

**Error `403`:** not a central admin, or the organisation is suspended.
```json
{ "detail": "You do not have permission to perform this action." }
```

---

### Add Member

| | |
|---|---|
| **Method / URL** | `POST /api/orgs/members/` |
| **Auth** | Bearer access token — **central admin** of an active org |

Creates the account with an unusable password and sends the welcome /
get-started email. `slug` is generated — do not send it.

**Request:**
```json
{
  "email": "alice@acme.com",
  "first_name": "Alice",
  "last_name": "Smith",
  "phone": "+15551234",
  "user_type": "warehouse_manager"
}
```

`phone` is optional. `user_type` must be `central_admin` or `warehouse_manager`.

**Success `201`:**
```json
{
  "slug": "alice-smith",
  "email": "alice@acme.com",
  "user_type": "warehouse_manager",
  "first_name": "Alice",
  "last_name": "Smith",
  "phone": "+15551234",
  "full_name": "Alice Smith",
  "is_active": true,
  "has_usable_password": false,
  "date_joined": "2026-09-15T10:00:00Z"
}
```

**Error `400` — duplicate email:**
```json
{ "email": ["A user with this email already exists."] }
```

**Error `400` — invalid user type:**
```json
{ "user_type": ["\"super_admin\" is not a valid choice."] }
```

**Error `401`:** see [Shared Error Responses](#401--not-authenticated)

**Error `403`:** not a central admin, or the organisation is suspended.
```json
{ "detail": "You do not have permission to perform this action." }
```

---

### Resend Welcome Email

| | |
|---|---|
| **Method / URL** | `POST /api/orgs/members/{slug}/resend-welcome/` |
| **Auth** | Bearer access token — **central admin** of an active org |

`{slug}` is the member's `UserProfile.slug`. No request body. Only members who
have **not** set a password yet can be resent.

**Success `200`:**
```json
{ "detail": "Welcome email sent." }
```

**Error `400` — password already set:**
```json
{ "detail": "This user has already set a password." }
```

**Error `401`:** see [Shared Error Responses](#401--not-authenticated)

**Error `403`:** not a central admin, or the organisation is suspended.
```json
{ "detail": "You do not have permission to perform this action." }
```

**Error `404` — unknown slug, or the member belongs to another organisation:**
```json
{ "detail": "Not found." }
```

---

### Suspend Member

| | |
|---|---|
| **Method / URL** | `POST /api/orgs/members/{slug}/suspend/` |
| **Auth** | Bearer access token — **central admin** of an active org |

No request body. Sets `is_active` to `false`. The member cannot log in afterwards.
You cannot suspend your own account.

**Success `200`:**
```json
{ "detail": "User suspended." }
```

**Error `400` — already suspended:**
```json
{ "detail": "This user is already suspended." }
```

**Error `400` — cannot suspend self:**
```json
{ "detail": "You cannot suspend your own account." }
```

**Error `401`:** see [Shared Error Responses](#401--not-authenticated)

**Error `403`:** not a central admin, or the organisation is suspended.
```json
{ "detail": "You do not have permission to perform this action." }
```

**Error `404` — unknown slug, or the member belongs to another organisation:**
```json
{ "detail": "Not found." }
```

---

### Unsuspend Member

| | |
|---|---|
| **Method / URL** | `POST /api/orgs/members/{slug}/unsuspend/` |
| **Auth** | Bearer access token — **central admin** of an active org |

No request body. Sets `is_active` to `true`.

**Success `200`:**
```json
{ "detail": "User unsuspended." }
```

**Error `400` — not suspended:**
```json
{ "detail": "This user is not suspended." }
```

**Error `401`:** see [Shared Error Responses](#401--not-authenticated)

**Error `403`:** not a central admin, or the organisation is suspended.
```json
{ "detail": "You do not have permission to perform this action." }
```

**Error `404` — unknown slug, or the member belongs to another organisation:**
```json
{ "detail": "Not found." }
```

---

## Spaces

Central admins create spaces and assign `space_incharge` members. Operation
incharges may **GET** every space. Assigned space incharges may **GET** only
their space. Warehouse managers receive `403`. Public identifier is **`slug`**.

### List Spaces

| | |
|---|---|
| **Method / URL** | `GET /api/orgs/spaces/` |
| **Auth** | Bearer — central admin, operation incharge, or space incharge of an active org |

Paginated. Optional `status=active` or `status=suspended`.

**Success `200`:**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "slug": "north-wing",
      "name": "North Wing",
      "location": "Building A",
      "is_active": true,
      "created_at": "2026-09-17T10:00:00Z",
      "updated_at": "2026-09-17T10:00:00Z"
    }
  ]
}
```

**Error `400` — invalid status:**
```json
{ "status": ["Must be \"active\" or \"suspended\"."] }
```

**Error `401` / `403`:** as members.

---

### Create Space

| | |
|---|---|
| **Method / URL** | `POST /api/orgs/spaces/` |
| **Auth** | Bearer — **central admin** of an active org |

`slug` is generated. Do not send incharges here.

**Request:**
```json
{ "name": "North Wing", "location": "Building A" }
```

**Success `201`:** same object shape as a list item.

**Error `400` — duplicate name in this org:**
```json
{ "name": ["A space with this name already exists."] }
```

---

### Get / Update Space

| | |
|---|---|
| **GET / PATCH** | `/api/orgs/spaces/{slug}/` |
| **Auth GET** | Bearer — central admin, operation incharge, or the assigned space incharge |
| **Auth PATCH** | Bearer — **central admin** |

PATCH any subset of `name`, `location`. `slug` and `is_active` are not writable
here (use suspend/unsuspend).

**Success `200`:** space object (no `id`).

**Error `404`:**
```json
{ "detail": "Not found." }
```

---

### Suspend / Unsuspend Space

| | |
|---|---|
| **POST** | `/api/orgs/spaces/{slug}/suspend/` and `.../unsuspend/` |
| **Auth** | Bearer — **central admin** |

No request body.

**Success `200`:**
```json
{ "detail": "Space suspended." }
```
```json
{ "detail": "Space unsuspended." }
```

**Error `400` — already in that state:**
```json
{ "detail": "This space is already suspended." }
```

---

### List / Assign Space Incharges

| | |
|---|---|
| **GET / POST** | `/api/orgs/spaces/{slug}/incharges/` |
| **Auth GET** | Bearer — central admin, operation incharge, or assigned space incharge |
| **Auth POST** | Bearer — **central admin** |

GET is not paginated — an array of member objects. POST assigns one
`space_incharge` member. Each space incharge may be on at most one space.

**Request:**
```json
{ "member": "jane-doe" }
```

**Success `200`:** member object with `space: { "slug": "north-wing", "name": "North Wing" }`.

**Error `400` — wrong role:**
```json
{ "member": ["Only a space incharge can be assigned to a space."] }
```

**Error `400` — already assigned:**
```json
{ "detail": "This member is already assigned to this space." }
```

---

### Unassign Space Incharge

| | |
|---|---|
| **Method / URL** | `POST /api/orgs/spaces/{slug}/incharges/{member}/unassign/` |
| **Auth** | Bearer — **central admin** |

No request body.

**Success `200`:**
```json
{ "detail": "Space incharge unassigned." }
```

**Error `400` — not assigned:**
```json
{ "detail": "This member is not assigned to this space." }
```

---

## Vendors

Central admins, operation incharges, **and** warehouse managers manage vendors
in **their own organisation**. Space incharges receive `403`. There is no
delete — suspend instead. Public identifier is **`slug`**. Super admins
receive `403`. Vendors are contact records only (no vendor login).

### List Vendors

| | |
|---|---|
| **Method / URL** | `GET /api/orgs/vendors/` |
| **Auth** | Bearer — central admin, operation incharge, or warehouse manager of an active org |

Paginated. Optional `status=active` or `status=suspended`.

**Success `200`:**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "slug": "acme-supplies",
      "name": "Acme Supplies",
      "contact_name": "Jane Doe",
      "phone": "+15551234",
      "email": "jane@acme.com",
      "address": "12 Warehouse Rd",
      "gst": "22AAAAA0000A1Z5",
      "website": "https://acme.example",
      "is_active": true,
      "created_at": "2026-09-16T10:00:00Z",
      "updated_at": "2026-09-16T10:00:00Z"
    }
  ]
}
```

**Error `400` — invalid status:**
```json
{ "status": ["Must be \"active\" or \"suspended\"."] }
```

**Error `401`:** see [Shared Error Responses](#401--not-authenticated)

**Error `403`:**
```json
{ "detail": "You do not have permission to perform this action." }
```

---

### Add Vendor

| | |
|---|---|
| **Method / URL** | `POST /api/orgs/vendors/` |
| **Auth** | Bearer — central admin, operation incharge, or warehouse manager of an active org |

`slug` is generated. Required: `name`, `contact_name`, `phone`, `address`.
Optional: `email`, `gst`, `website`.

**Request:**
```json
{
  "name": "Acme Supplies",
  "contact_name": "Jane Doe",
  "phone": "+15551234",
  "address": "12 Warehouse Rd",
  "email": "jane@acme.com",
  "gst": "22AAAAA0000A1Z5",
  "website": "https://acme.example"
}
```

**Success `201`:** same object shape as a list item.

**Error `400` — duplicate name in this org:**
```json
{ "name": ["A vendor with this name already exists."] }
```

**Error `401` / `403`:** as list.

---

### Get Vendor

| | |
|---|---|
| **Method / URL** | `GET /api/orgs/vendors/{slug}/` |
| **Auth** | Bearer — central admin, operation incharge, or warehouse manager of an active org |

**Success `200`:** vendor object (no `id`).

**Error `404`:**
```json
{ "detail": "Not found." }
```

---

### Update Vendor

| | |
|---|---|
| **Method / URL** | `PATCH /api/orgs/vendors/{slug}/` |
| **Auth** | Bearer — central admin, operation incharge, or warehouse manager of an active org |

Any subset of create fields. `slug`, `org`, and `is_active` are not writable
here (use suspend/unsuspend).

**Request:**
```json
{ "phone": "+1999" }
```

**Success `200`:** updated vendor object.

**Error `400` — duplicate name:**
```json
{ "name": ["A vendor with this name already exists."] }
```

**Error `404`:**
```json
{ "detail": "Not found." }
```

---

### Suspend Vendor

| | |
|---|---|
| **Method / URL** | `POST /api/orgs/vendors/{slug}/suspend/` |
| **Auth** | Bearer — central admin, operation incharge, or warehouse manager of an active org |

No request body.

**Success `200`:**
```json
{ "detail": "Vendor suspended." }
```

**Error `400` — already suspended:**
```json
{ "detail": "This vendor is already suspended." }
```

**Error `404`:**
```json
{ "detail": "Not found." }
```

---

### Unsuspend Vendor

| | |
|---|---|
| **Method / URL** | `POST /api/orgs/vendors/{slug}/unsuspend/` |
| **Auth** | Bearer — central admin, operation incharge, or warehouse manager of an active org |

No request body.

**Success `200`:**
```json
{ "detail": "Vendor unsuspended." }
```

**Error `400` — not suspended:**
```json
{ "detail": "This vendor is not suspended." }
```

**Error `404`:**
```json
{ "detail": "Not found." }
```

---

## Warehouses

Org storage locations. Purchases land here first; issuing stock to Spaces is a
later API. Public identifier is **`slug`**. List/retrieve: central admin,
operation incharge, warehouse manager. Create/update: central admin and
warehouse manager. Space incharges receive `403`.

Registering an org auto-creates a warehouse named `Warehouse`.

### List / Create Warehouses

| | |
|---|---|
| **Method / URL** | `GET / POST /api/orgs/warehouses/` |
| **Auth GET** | Bearer — central admin, operation incharge, or warehouse manager |
| **Auth POST** | Bearer — central admin or warehouse manager |

Paginated. Optional `status=active` or `status=suspended`.

**Request (POST):**
```json
{ "name": "South store", "location": "Dock 2" }
```

**Success `201`:**
```json
{
  "slug": "south-store",
  "name": "South store",
  "location": "Dock 2",
  "is_active": true,
  "created_at": "2026-09-17T10:00:00Z",
  "updated_at": "2026-09-17T10:00:00Z"
}
```

**Error `400` — duplicate name:**
```json
{ "name": ["A warehouse with this name already exists."] }
```

### Get / Update Warehouse

| | |
|---|---|
| **GET / PATCH** | `/api/orgs/warehouses/{slug}/` |
| **Auth GET** | Bearer — central admin, operation incharge, or warehouse manager |
| **Auth PATCH** | Bearer — central admin or warehouse manager |

PATCH any subset of `name`, `location`, `is_active`.

---

## Item categories

Reusable org-wide categories. Items in different warehouses can share one.

### List / Create Categories

| | |
|---|---|
| **Method / URL** | `GET / POST /api/orgs/item-categories/` |
| **Auth GET** | Bearer — central admin, operation incharge, or warehouse manager |
| **Auth POST** | Bearer — central admin or warehouse manager |

**Request (POST):**
```json
{ "name": "Stationery" }
```

**Success `201`:** `{ "slug": "stationery", "name": "Stationery", "is_active": true, "created_at": "...", "updated_at": "..." }`

**Error `400` — duplicate name:**
```json
{ "name": ["A category with this name already exists."] }
```

### Get / Update Category

| | |
|---|---|
| **GET / PATCH** | `/api/orgs/item-categories/{slug}/` |

PATCH `name` and/or `is_active`.

---

## Items

Warehouse catalog. Each item belongs to **one warehouse**. `quantity_on_hand`
is **not** writable on create or PATCH — stock changes only when a warehouse
receipt is completed. `balance_in_stock` equals `quantity_on_hand` until
reservations exist. Photos are optional (max 5); uploads are stored as WebP.

List/retrieve: central admin, operation incharge, warehouse manager.
Create/update/suspend/photos: central admin and warehouse manager. Space
incharges receive `403`. Public identifier is **`slug`**.

### List Items

| | |
|---|---|
| **Method / URL** | `GET /api/orgs/items/` |
| **Auth** | Bearer — central admin, operation incharge, or warehouse manager |

Paginated. Optional `status=active` or `status=suspended`. Optional
`warehouse={slug}`.

**Success `200`:**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "slug": "a4-paper",
      "warehouse": "warehouse",
      "name": "A4 paper",
      "description": "80gsm copier paper",
      "part_number": "PAP-A4",
      "alternate_part_number": "",
      "unit": "ream",
      "category": "stationery",
      "location": "Aisle 2 / Bin 4",
      "remarks": "",
      "quantity_on_hand": "0.000",
      "balance_in_stock": "0.000",
      "last_purchase_date": null,
      "last_purchase_quantity": null,
      "photos": [],
      "is_active": true,
      "created_at": "2026-09-17T10:00:00Z",
      "updated_at": "2026-09-17T10:00:00Z"
    }
  ]
}
```

**Error `400` — invalid status:**
```json
{ "status": ["Must be \"active\" or \"suspended\"."] }
```

**Error `400` — unknown warehouse filter:**
```json
{ "warehouse": ["Unknown warehouse."] }
```

---

### Create Item

| | |
|---|---|
| **Method / URL** | `POST /api/orgs/items/` |
| **Auth** | Bearer — central admin or warehouse manager |

`slug` is generated. `warehouse` is required (slug). `quantity_on_hand` is
ignored if sent. Name and `part_number` (when non-blank) are unique per
warehouse.

**Request:**
```json
{
  "warehouse": "warehouse",
  "name": "A4 paper",
  "description": "80gsm copier paper",
  "part_number": "PAP-A4",
  "alternate_part_number": "",
  "unit": "ream",
  "category": "stationery",
  "location": "Aisle 2 / Bin 4",
  "remarks": ""
}
```

**Success `201`:** item object with `"quantity_on_hand": "0.000"` and
`"photos": []`.

**Error `400` — duplicate name:**
```json
{ "name": ["An item with this name already exists."] }
```

**Error `400` — missing warehouse:**
```json
{ "warehouse": ["This field is required."] }
```

---

### Get / Update Item

| | |
|---|---|
| **GET / PATCH** | `/api/orgs/items/{slug}/` |
| **Auth GET** | Bearer — central admin, operation incharge, or warehouse manager |
| **Auth PATCH** | Bearer — central admin or warehouse manager |

PATCH any subset of `warehouse`, `name`, `description`, `part_number`,
`alternate_part_number`, `unit`, `category`, `location`, `remarks`,
`last_purchase_date`, `last_purchase_quantity`. `quantity_on_hand` is not
writable. Last-purchase fields also auto-update when a receipt is completed.

**Success `200`:** item object (no `id`).

---

### Item photos

| | |
|---|---|
| **POST** | `/api/orgs/items/{slug}/photos/` (multipart field `image`) |
| **DELETE** | `/api/orgs/items/{slug}/photos/{photo_slug}/` |
| **Auth** | Bearer — central admin or warehouse manager |

JPEG, PNG, GIF, or WebP in; stored as WebP. Maximum 5 photos per item.

**Success `201`:**
```json
{ "slug": "aisle-bin", "url": "http://localhost:8000/media/items/2026/09/aisle-bin.webp" }
```

**Error `400` — sixth photo:**
```json
{ "detail": "An item can have at most 5 photos." }
```

**Success `204`:** empty body on delete.

---

### Suspend / Unsuspend Item

| | |
|---|---|
| **POST** | `/api/orgs/items/{slug}/suspend/` and `.../unsuspend/` |
| **Auth** | Bearer — central admin or warehouse manager |

**Success `200`:** `{ "detail": "Item suspended." }` / `{ "detail": "Item unsuspended." }`

**Error `400`:** `{ "detail": "This item is already suspended." }`

---

## Purchases

Record-keeping for offline deals. Vendors never log in. Public identifiers are
**`slug`**. Ops-raised PRs auto-approve on submit. Space-raised PRs wait for
ops approve / decline / request-revision.

Roles:

- Create/list PRs: assigned `space_incharge` (their space only),
  `operation_incharge`, `central_admin`
- RFQ, quotes, select lines, POs, QC, invoice, trail, verify: ops or central admin
- Warehouse receipts: warehouse manager or central admin
- Export: ops and central admin on PR/RFQ/PO/invoice; space incharge on **their**
  PRs; warehouse on receipts

### List / Create Purchase Requests

| | |
|---|---|
| **Method / URL** | `GET / POST /api/orgs/purchase-requests/` |
| **Auth** | Bearer — space incharge, operation incharge, or central admin |

`lines` is required (min 1). Space incharges omit `space` (it is implied). Ops
may send `space` or omit/`null`. `item` on a line is optional.

**Request:**
```json
{
  "title": "Q3 pantry restock",
  "space": "north-wing",
  "notes": "",
  "lines": [
    { "description": "A4 paper", "quantity": "10", "unit": "ream", "item": "a4-paper" },
    { "description": "Blue pens", "quantity": "50", "unit": "pcs" }
  ]
}
```

**Success `201`:**
```json
{
  "slug": "q3-pantry-restock",
  "title": "Q3 pantry restock",
  "status": "draft",
  "notes": "",
  "space": "north-wing",
  "created_by": "op-lead",
  "review_reason": "",
  "lines": [
    {
      "slug": "a4-paper",
      "description": "A4 paper",
      "quantity": "10.000",
      "unit": "ream",
      "item": "a4-paper",
      "awarded_vendor": null
    }
  ],
  "created_at": "2026-09-17T10:00:00Z",
  "updated_at": "2026-09-17T10:00:00Z"
}
```

GET is paginated; list items use the same shape (nested `lines`).

**Error `400` — empty lines:**
```json
{ "lines": ["A purchase request must include at least one line."] }
```

**Error `400` — unassigned space incharge:**
```json
{ "space": ["Assign this space incharge to a space before creating a request."] }
```

---

### Get / Patch Purchase Request

| | |
|---|---|
| **GET / PATCH** | `/api/orgs/purchase-requests/{slug}/` |
| **Auth** | Bearer — same as list; space incharge scoped to their space |

PATCH may replace `title`, `notes`, and the full `lines` array while `draft` or
`revision_requested`.

**Error `400`:**
```json
{ "detail": "This action is not allowed in the current status." }
```

---

### Submit / Approve / Decline / Request Revision

| | |
|---|---|
| **POST** | `/api/orgs/purchase-requests/{slug}/submit/` |
| **Auth submit** | Creator, or ops/central admin |
| **POST approve** | `/api/orgs/purchase-requests/{slug}/approve/` — ops or central admin |
| **POST decline** | `/api/orgs/purchase-requests/{slug}/decline/` — body `{ "reason": "..." }` |
| **POST revision** | `/api/orgs/purchase-requests/{slug}/request-revision/` — body `{ "reason": "..." }` |

Submit on an ops-raised PR returns `"status": "approved"`. Space-raised submit
returns `"status": "submitted"`. Decline archives (`declined`).

**Error `400` — missing reason:**
```json
{ "reason": ["A reason is required."] }
```

---

### Process Trail

| | |
|---|---|
| **Method / URL** | `GET /api/orgs/purchase-requests/{slug}/trail/` |
| **Auth** | Bearer — operation incharge or central admin |

Ordered events. Each has `action`, `actor_slug`, `actor_user_type`,
`content_hash`, `signature`, `prev_hash` (`"genesis"` on the first event).

**Success `200`:** array of event objects.

---

### Export Purchase Request

| | |
|---|---|
| **Method / URL** | `GET /api/orgs/purchase-requests/{slug}/export/?format=pdf` or `xlsx` |
| **Auth** | Bearer — ops/central admin, or space incharge for their own PRs |

`format` is required. PDF is `application/pdf` with wet-ink signature boxes.
Excel starts with ZIP magic (`PK`).

**Error `400`:**
```json
{ "format": ["Must be \"pdf\" or \"xlsx\"."] }
```

---

### RFQs

| | |
|---|---|
| **GET / POST** | `/api/orgs/rfqs/` |
| **GET detail** | `/api/orgs/rfqs/{slug}/` |
| **Auth** | Bearer — operation incharge or central admin |

POST from an **approved** PR. No emails are sent.

**Request:**
```json
{
  "purchase_request": "q3-pantry-restock",
  "vendor_slugs": ["acme-supplies", "office-mart"]
}
```

**Success `201`:** RFQ with `vendors[]` and `lines[]` (each line includes competing
`quotes: [{ "vendor", "unit_price" }]`).

**Error `400` — no vendors:**
```json
{ "vendor_slugs": ["Choose at least one existing active vendor, or add vendors first."] }
```

**Error `400` — PR not approved:**
```json
{ "purchase_request": ["The purchase request must be approved first."] }
```

Further RFQ actions (all ops/central admin):

| Method | URL | Body |
|---|---|---|
| POST | `/api/orgs/rfqs/{slug}/vendors/` | `{ "vendor": "<slug>" }` |
| POST | `/api/orgs/rfqs/{slug}/vendors/{vendor_slug}/reject/` | `{ "reason": "..." }` |
| POST | `/api/orgs/rfqs/{slug}/quotes/` | `{ "vendor": "<slug>", "lines": [{ "line": "<pr-line-slug>", "unit_price": "12.50" }] }` |
| POST | `/api/orgs/rfqs/{slug}/request-revision/` | empty — RFQ back to `preparing` |
| POST | `/api/orgs/rfqs/{slug}/select-lines/` | `{ "selections": [{ "line": "<slug>", "vendor": "<slug>" }] }` |
| POST | `/api/orgs/rfqs/{slug}/purchase-orders/` | `{ "vendor": "<slug>", "create_purchase_order": true }` |
| GET | `/api/orgs/rfqs/{slug}/export/?format=pdf\|xlsx` | quote comparison |

**Error `400` — select a vendor with no quote on that line:**
```json
{ "vendor": ["This vendor has no recorded quote for that line."] }
```

**Error `400` — line already awarded:**
```json
{ "line": ["This line is already awarded."] }
```

`create_purchase_order: false` still creates a PO row with `"is_new_order": false`
so QC and warehouse have a target.

---

### Purchase Orders

| | |
|---|---|
| **GET list / detail** | `/api/orgs/purchase-orders/` and `/api/orgs/purchase-orders/{slug}/` |
| **Auth** | Bearer — operation incharge or central admin |

One PO per winning vendor. **Success `200`:** `{ slug, vendor, purchase_request,
status, is_new_order, lines[], created_at, updated_at }`.

**Quality check** `POST /api/orgs/purchase-orders/{slug}/quality-check/`

```json
{ "passed": true, "reason": "", "next": "return" }
```

On fail, `reason` is required. `next` is `return` (stay on vendor),
`reorder_same`, or `choose_vendors` (unaward those lines). Pass creates a
pending warehouse receipt.

**Invoice** `POST /api/orgs/purchase-orders/{slug}/invoice/` (after QC pass)

```json
{ "notes": "Filed offline", "document_urls": ["https://example.com/inv.pdf"] }
```

**Success `200`:** `{ slug, notes, document_urls, status: "pending_payment", created_at }`

Exports: `/api/orgs/purchase-orders/{slug}/export/?format=pdf|xlsx` and
`/api/orgs/purchase-orders/{slug}/invoice/export/?format=pdf|xlsx`.

---

### Warehouse Receipts

| | |
|---|---|
| **GET list / detail** | `/api/orgs/warehouse/receipts/` and `.../{slug}/` |
| **Auth** | Bearer — warehouse manager or central admin |

Optional `?status=pending` or `completed`.

Each pending line includes prompt fields for the warehouse UI:

- `source_item` — original PR catalog item slug when it still belongs to the
  receipt warehouse; otherwise `null`
- `suggested_items` — up to 5 active items in that warehouse whose `name`
  matches the line `description` (case-insensitive), including `source_item`
  when present. Empty when the receipt has no warehouse yet (re-GET after
  sending `warehouse` on complete, or when the org has one warehouse so it is
  set at QC)

**Success `200` (pending line excerpt):**
```json
{
  "slug": "recv-po-a4-paper",
  "description": "A4 paper",
  "quantity": "10.000",
  "unit": "ream",
  "item": null,
  "source_item": "a4-paper",
  "suggested_items": [
    {
      "slug": "a4-paper",
      "name": "A4 paper",
      "part_number": "PAP-A4",
      "unit": "ream",
      "quantity_on_hand": "3.000"
    }
  ]
}
```

Prompt:

- `suggested_items` present → ask whether to add stock to that item or create a
  new catalog item
- empty → only offer create as a new item (confirm)

**Complete** `POST /api/orgs/warehouse/receipts/{slug}/complete/` — every receipt
line must be included. Mix `new_item` and `add_to_existing` per line. Stock is
always credited to the receipt warehouse (never a Space). If the org has one
active warehouse, it is set when the receipt is created; otherwise send
`warehouse`.

```json
{
  "warehouse": "warehouse",
  "lines": [
    { "line": "a4-receipt-line", "action": "new_item", "name": "A4 paper stock", "unit": "ream", "part_number": "PAP-A4" },
    { "line": "pens-receipt-line", "action": "add_to_existing", "item": "blue-pens" }
  ]
}
```

**Success `200`:** receipt with `"status": "completed"`, `"warehouse"`, and `item`
slugs filled. Completing also stamps `last_purchase_date` and
`last_purchase_quantity` on the item. `new_item` with a duplicate name in that
warehouse returns 400 from the catalog.

**Error `400`:**
```json
{ "lines": ["Every receipt line must be included."] }
```

**Error `400` — item in another warehouse:**
```json
{ "item": "This item is not in the receipt warehouse." }
```

Export: `GET /api/orgs/warehouse/receipts/{slug}/export/?format=pdf|xlsx`.

---

### Verify Process Event

| | |
|---|---|
| **Method / URL** | `POST /api/orgs/process-events/verify/` |
| **Auth** | Bearer — operation incharge or central admin |

```json
{ "content_hash": "<sha256 hex>", "signature": "<hmac hex>" }
```

**Success `200`:**
```json
{ "valid": true }
```

Tampered signatures return `{ "valid": false }`.

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

> All outstanding refresh tokens for this user are blacklisted and the `inveno_refresh` cookie is cleared. The client must log in again.

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

> All outstanding refresh tokens for this user are blacklisted. Existing sessions must log in again.

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

## Token Storage

| Token | Where | Notes |
|---|---|---|
| Access (15 min) | In-memory only | React context / module variable — never `localStorage` |
| Refresh (7 days) | httpOnly cookie `inveno_refresh` | Set by API on login/refresh; `Path=/api/auth/`; JS cannot read it |

### Client requirements

1. `axios.create({ withCredentials: true })` (or `fetch` with `credentials: 'include'`)
2. Store `access` in memory after login or silent refresh
3. On app load, call `POST /api/auth/token/refresh/` with credentials (empty body)
4. On `401`, try one silent refresh; on failure redirect to `/login`
5. Do **not** refresh on `403` (permission denied, not expired token)

See the full React/Vite/TS kit in [`apps/common/frontend_guide.md`](apps/common/frontend_guide.md) (also at `/api/docs/frontend/`).

---

## Code Examples

### Axios setup (recommended)

```js
// src/lib/auth.js — access in memory only
let accessToken = null;
export const getAccessToken = () => accessToken;
export const setAccessToken = (token) => { accessToken = token; };
export const clearAccessToken = () => { accessToken = null; };
```

```js
// src/lib/api.js
import axios from 'axios';
import { getAccessToken, setAccessToken, clearAccessToken } from './auth';

const baseURL = import.meta.env.VITE_API_URL;

export const api = axios.create({
  baseURL,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const access = getAccessToken();
  if (access) config.headers.Authorization = `Bearer ${access}`;
  return config;
});

let refreshing = null;

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      try {
        if (!refreshing) {
          refreshing = axios
            .post(`${baseURL}/api/auth/token/refresh/`, {}, { withCredentials: true })
            .then((r) => {
              setAccessToken(r.data.access);
              return r.data.access;
            })
            .finally(() => { refreshing = null; });
        }
        const access = await refreshing;
        original.headers.Authorization = `Bearer ${access}`;
        return api(original);
      } catch {
        clearAccessToken();
        window.location.assign('/login');
      }
    }
    return Promise.reject(error);
  }
);
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
  setAccessToken(data.access); // refresh is in httpOnly cookie
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
  try {
    await api.post('/api/auth/logout/');
  } finally {
    clearAccessToken();
  }
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
| 1.2.0 | 2026-09-15 | Org member API: list/add/resend welcome (`/api/orgs/members/`); `warehouse_manager` role |
| 1.3.0 | 2026-09-16 | Suspend / unsuspend members; `?status=` filter; login `400` for suspended accounts |
| 1.4.0 | 2026-09-16 | Vendor API: list/add/get/update/suspend (`/api/orgs/vendors/`) |
| 1.5.0 | 2026-09-17 | Spaces, `operation_incharge` / `space_incharge`, item catalog, purchase flow (RFQ, per-line award, PO, QC, warehouse, HMAC trail, PDF/Excel) |
| 1.6.0 | 2026-09-18 | Warehouses, item categories, catalog fields, WebP photos (max 5), receipts credit a warehouse |
| 1.7.0 | 2026-09-18 | Receipt GET `source_item` / `suggested_items` so the UI can prompt add-stock vs new item |
| 1.8.0 | 2026-09-22 | Duplicate slugs use `{base}-{YYYYMMDD}-{letter}` (local date, no time, no `-2`) |
