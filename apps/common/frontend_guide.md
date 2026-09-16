# Frontend guide (React + Vite + TypeScript)

How to build the Inveno web app against this API. Per-endpoint JSON lives in
`FRONTEND_API.md`. The **Current endpoints** table below is generated from the
live OpenAPI schema and updates automatically when the API changes.

Log in at `/admin/` first — this page is staff-only, same as Swagger.

---

## 1. Roles

There is **no public register**. Super admins create organisations and the first
central admin in Django Admin. Central admins then add further org users via
`POST /api/orgs/members/`.

| `user_type` | Staff? | `org` | What they can do in the UI |
|---|---|---|---|
| `super_admin` | yes | always `null` | Platform admin; no org-scoped screens |
| `central_admin` | no | required | Org-scoped app, including member management; blocked if `org.is_active` is false |
| `warehouse_manager` | no | required | Org-scoped app including vendors; **cannot** manage members; blocked if `org.is_active` is false |

Use `GET /api/auth/me/` as the source of truth for routing. JWT claims are a
hint for the first paint only.

---

## 2. Onboarding

1. Super admin creates the org + first central admin in `/admin/`.
2. A central admin may add more users (`central_admin` or `warehouse_manager`)
   with `POST /api/orgs/members/`.
3. The API emails a Get Started link: `{FRONTEND_URL}/get-started?uid=...&token=...`
   (`FRONTEND_URL` defaults to `http://localhost:5173`).
4. The Get Started page calls `POST /api/auth/password/set/` (public, 7-day
   one-time token).
5. Then `POST /api/auth/login/` with email + password.
6. Store the JWT pair and call `GET /api/auth/me/`.

The password-set token is **not** the same as the forgot-password token.

---

## 3. JWT session

| Token | Lifetime | Where it goes |
|---|---|---|
| Access | 15 minutes | `Authorization: Bearer <access>` |
| Refresh | 7 days | body of refresh/logout only — never in the header |

Refresh **rotates**: each `POST /api/auth/token/refresh/` returns a new
`access` **and** a new `refresh`. Persist the new refresh. The old one is
blacklisted.

Recommended storage: memory for access, `httpOnly` cookie for refresh if you
control a BFF; for a pure SPA, `sessionStorage` is acceptable. Do not put
tokens in `localStorage` if you can avoid it (XSS).

On `POST /api/auth/logout/` send the refresh token in the JSON body **and** the
access token in the Authorization header, then clear local state.

---

## 4. JWT claims vs `/me`

Access-token payload (after the standard `exp` / `token_type` fields):

```json
{
  "user_id": "uuid",
  "user_type": "central_admin",
  "org_id": "uuid-of-org",
  "org_suffix": "acme_west"
}
```

For `super_admin`, `org_id` and `org_suffix` are `null`.

Still call `GET /api/auth/me/` after login. `/me` includes names, phone, and
`org.is_active`, which claims do not.

---

## 5. Authorization

| Surface | Auth |
|---|---|
| `GET /api/health/` | Public |
| `POST /api/auth/login/`, refresh, verify, password set/reset | Public (throttled 10/min) |
| Most `/api/auth/*` | `IsAuthenticated` (Bearer) |
| `GET/POST /api/orgs/members/`, resend welcome, suspend, unsuspend | Central admin of an active org |
| `/api/orgs/vendors/` (list/add/get/patch/suspend) | Central admin or warehouse manager of an active org |
| `/api/docs/`, `/api/docs/frontend/`, `/api/redoc/`, `/api/schema/` | Staff session or staff JWT |

If the org is suspended, login returns `400`:

```json
{
  "non_field_errors": [
    "Your organisation has been suspended. Please contact your administrator."
  ]
}
```

If the **account** is suspended, login returns `400`:

```json
{
  "non_field_errors": [
    "Your account has been suspended. Please contact your administrator."
  ]
}
```

Gate org UI with `central_admin` **or** `warehouse_manager` and `org?.is_active`.
Gate **member management** (list/add/resend) with `profile.user_type === "central_admin"`.
Vendor screens are allowed for both org roles.
A `403` from any authenticated route means the user is logged in but not allowed
— do not try to refresh the token for that.

---

## 6. Forgot password vs set-password

| | Set password (welcome email) | Forgot password |
|---|---|---|
| Endpoint | `POST /api/auth/password/set/` | `POST /api/auth/password/reset/` then `.../reset/confirm/` |
| Token TTL | 7 days | 1 hour |
| One-time | Yes (invalid once a usable password exists) | Yes after confirm |

Do not reuse Get Started tokens on the forgot-password page.

---

## 7. Frontend checklist

1. Axios (or fetch) instance with `baseURL = import.meta.env.VITE_API_URL`.
2. Attach `Authorization: Bearer` on every request except the public auth ones.
3. On `401`, try **one** refresh; queue concurrent 401s; if refresh fails, logout.
4. Show a banner on `403` and `429` (`Retry-After` header, seconds).
5. Browser talks to `http://localhost:8000`, **never** `http://api:8000` (that
   hostname only exists on the Docker network).

---

## 8. React + Vite + TypeScript

### Env

`.env` (Vite only exposes `VITE_*`):

```env
VITE_API_URL=http://localhost:8000
```

`src/vite-env.d.ts`:

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

Install the HTTP client: `npm i axios`.

### Types

```ts
export type UserType = "super_admin" | "central_admin" | "warehouse_manager";
export type OrgAssignableUserType = "central_admin" | "warehouse_manager";

export const ORG_USER_TYPES: UserType[] = ["central_admin", "warehouse_manager"];

export type TokenPair = {
  access: string;
  refresh: string;
};

export type JwtClaims = {
  user_id: string;
  user_type: UserType | null;
  org_id: string | null;
  org_suffix: string | null;
};

export type MeResponse = {
  id: string;
  email: string;
  date_joined: string;
  updated_at: string;
  profile: {
    user_type: UserType;
    first_name: string;
    last_name: string;
    phone: string;
    full_name: string;
  } | null;
  org: {
    id: string;
    name: string;
    org_suffix: string;
    location: string;
    is_active: boolean;
    registered_on: string;
  } | null;
};

export type OrgMember = {
  slug: string;
  email: string;
  user_type: OrgAssignableUserType;
  first_name: string;
  last_name: string;
  phone: string;
  full_name: string;
  is_active: boolean;
  has_usable_password: boolean;
  date_joined: string;
};

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type Vendor = {
  slug: string;
  name: string;
  contact_name: string;
  phone: string;
  email: string;
  address: string;
  gst: string;
  website: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type VendorWrite = {
  name: string;
  contact_name: string;
  phone: string;
  address: string;
  email?: string;
  gst?: string;
  website?: string;
};
```

### `src/lib/api.ts`

Bearer interceptor, queued refresh-on-401, logout when refresh fails.

```ts
import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import type {
  MeResponse,
  OrgAssignableUserType,
  OrgMember,
  Paginated,
  TokenPair,
  Vendor,
  VendorWrite,
} from "./types";

const TOKEN_KEY = "inveno.tokens";

export function getTokens(): TokenPair | null {
  const raw = sessionStorage.getItem(TOKEN_KEY);
  return raw ? (JSON.parse(raw) as TokenPair) : null;
}

export function setTokens(tokens: TokenPair | null) {
  if (!tokens) sessionStorage.removeItem(TOKEN_KEY);
  else sessionStorage.setItem(TOKEN_KEY, JSON.stringify(tokens));
}

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const access = getTokens()?.access;
  if (access) {
    config.headers.Authorization = `Bearer ${access}`;
  }
  return config;
});

let refreshing: Promise<string> | null = null;

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    const status = error.response?.status;

    if (status === 401 && original && !original._retry) {
      original._retry = true;
      const refresh = getTokens()?.refresh;
      if (!refresh) {
        setTokens(null);
        return Promise.reject(error);
      }
      try {
        if (!refreshing) {
          refreshing = axios
            .post<TokenPair>(`${import.meta.env.VITE_API_URL}/api/auth/token/refresh/`, {
              refresh,
            })
            .then((r) => {
              setTokens(r.data);
              return r.data.access;
            })
            .finally(() => {
              refreshing = null;
            });
        }
        const access = await refreshing;
        original.headers.Authorization = `Bearer ${access}`;
        return api(original);
      } catch {
        setTokens(null);
        window.location.assign("/login");
        return Promise.reject(error);
      }
    }
    return Promise.reject(error);
  },
);

export async function login(email: string, password: string) {
  const { data } = await api.post<TokenPair>("/api/auth/login/", { email, password });
  setTokens(data);
  return data;
}

export async function setPassword(body: {
  uid: string;
  token: string;
  new_password: string;
  new_password2: string;
}) {
  const { data } = await api.post<{ detail: string }>("/api/auth/password/set/", body);
  return data;
}

export async function getMe() {
  const { data } = await api.get<MeResponse>("/api/auth/me/");
  return data;
}

export async function logout() {
  const refresh = getTokens()?.refresh;
  try {
    if (refresh) await api.post("/api/auth/logout/", { refresh });
  } finally {
    setTokens(null);
  }
}

export async function forgotPassword(email: string) {
  const { data } = await api.post<{ detail: string }>("/api/auth/password/reset/", {
    email,
  });
  return data;
}

export async function listOrgMembers(status?: "active" | "suspended") {
  const { data } = await api.get<Paginated<OrgMember>>("/api/orgs/members/", {
    params: status ? { status } : undefined,
  });
  return data;
}

export async function addOrgMember(body: {
  email: string;
  first_name: string;
  last_name: string;
  phone?: string;
  user_type: OrgAssignableUserType;
}) {
  const { data } = await api.post<OrgMember>("/api/orgs/members/", body);
  return data;
}

export async function resendWelcome(slug: string) {
  const { data } = await api.post<{ detail: string }>(
    `/api/orgs/members/${slug}/resend-welcome/`,
  );
  return data;
}

export async function suspendMember(slug: string) {
  const { data } = await api.post<{ detail: string }>(
    `/api/orgs/members/${slug}/suspend/`,
  );
  return data;
}

export async function unsuspendMember(slug: string) {
  const { data } = await api.post<{ detail: string }>(
    `/api/orgs/members/${slug}/unsuspend/`,
  );
  return data;
}

export async function listVendors(status?: "active" | "suspended") {
  const { data } = await api.get<Paginated<Vendor>>("/api/orgs/vendors/", {
    params: status ? { status } : undefined,
  });
  return data;
}

export async function addVendor(body: VendorWrite) {
  const { data } = await api.post<Vendor>("/api/orgs/vendors/", body);
  return data;
}

export async function getVendor(slug: string) {
  const { data } = await api.get<Vendor>(`/api/orgs/vendors/${slug}/`);
  return data;
}

export async function updateVendor(slug: string, body: Partial<VendorWrite>) {
  const { data } = await api.patch<Vendor>(`/api/orgs/vendors/${slug}/`, body);
  return data;
}

export async function suspendVendor(slug: string) {
  const { data } = await api.post<{ detail: string }>(
    `/api/orgs/vendors/${slug}/suspend/`,
  );
  return data;
}

export async function unsuspendVendor(slug: string) {
  const { data } = await api.post<{ detail: string }>(
    `/api/orgs/vendors/${slug}/unsuspend/`,
  );
  return data;
}
```

Skip the interceptor refresh for `/api/auth/token/refresh/` itself (the snippet
uses a bare `axios.post` for that reason).

### Route guard

```tsx
import { Navigate, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { getMe, getTokens } from "./lib/api";
import type { MeResponse, UserType } from "./lib/types";

const ORG_ROLES: UserType[] = ["central_admin", "warehouse_manager"];

export function RequireAuth({
  orgOnly = false,
  centralAdminOnly = false,
}: {
  orgOnly?: boolean;
  centralAdminOnly?: boolean;
}) {
  const [me, setMe] = useState<MeResponse | null | undefined>(undefined);

  useEffect(() => {
    if (!getTokens()) {
      setMe(null);
      return;
    }
    getMe().then(setMe).catch(() => setMe(null));
  }, []);

  if (me === undefined) return null;
  if (!me) return <Navigate to="/login" replace />;

  const role = me.profile?.user_type;

  if (orgOnly) {
    if (!role || !ORG_ROLES.includes(role)) {
      return <Navigate to="/admin-home" replace />;
    }
    if (!me.org?.is_active) {
      return <p>Your organisation has been suspended.</p>;
    }
  }

  if (centralAdminOnly && role !== "central_admin") {
    return <Navigate to="/" replace />;
  }

  return <Outlet context={{ me }} />;
}
```

- Unauthenticated → `/login`
- Org routes (`orgOnly`): `central_admin` or `warehouse_manager` + active org
- Member management (`centralAdminOnly`): `central_admin` only
- Inactive org → show suspended, do not render org UI
- `super_admin` → platform home, not org routes (`org` is `null`)

### Get Started page

Welcome emails point at `/get-started?uid=...&token=...`.

```tsx
import { FormEvent, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { setPassword } from "./lib/api";

export function GetStartedPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";
  const [new_password, setNew] = useState("");
  const [new_password2, setNew2] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await setPassword({ uid, token, new_password, new_password2 });
      navigate("/login");
    } catch (err: unknown) {
      setError("Link is invalid or has expired. Request a new welcome email.");
    }
  }

  return (
    <form onSubmit={onSubmit}>
      {error ? <p>{error}</p> : null}
      <input type="password" value={new_password} onChange={(e) => setNew(e.target.value)} />
      <input type="password" value={new_password2} onChange={(e) => setNew2(e.target.value)} />
      <button type="submit">Set password</button>
    </form>
  );
}
```

Success: `{ "detail": "Password set successfully. You can now log in." }` then
`POST /api/auth/login/`.
