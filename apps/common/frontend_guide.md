# Frontend guide (React + Vite + TypeScript)

How to build the Inveno web app against this API. Per-endpoint JSON lives in
`FRONTEND_API.md`. The **Current endpoints** table below is generated from the
live OpenAPI schema and updates automatically when the API changes.

Log in at `/admin/` first — this page is staff-only, same as Swagger.

---

## 1. Roles

There is **no public register**. Super admins create organisations and the first
central admin in Django Admin.

| `user_type` | Staff? | `org` | What they can do in the UI |
|---|---|---|---|
| `super_admin` | yes | always `null` | Platform admin; no org-scoped screens |
| `central_admin` | no | required | Org-scoped app; blocked if `org.is_active` is false |

Use `GET /api/auth/me/` as the source of truth for routing. JWT claims are a
hint for the first paint only.

---

## 2. Onboarding

1. Super admin creates the org + first central admin in `/admin/`.
2. The API emails a Get Started link: `{FRONTEND_URL}/get-started?uid=...&token=...`
   (`FRONTEND_URL` defaults to `http://localhost:5173`).
3. The Get Started page calls `POST /api/auth/password/set/` (public, 7-day
   one-time token).
4. Then `POST /api/auth/login/` with email + password.
5. Store the JWT pair and call `GET /api/auth/me/`.

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
| `/api/docs/`, `/api/docs/frontend/`, `/api/redoc/`, `/api/schema/` | Staff session or staff JWT |

If the org is suspended, login returns `400`:

```json
{
  "non_field_errors": [
    "Your organisation has been suspended. Please contact your administrator."
  ]
}
```

Gate org UI with `profile.user_type === "central_admin"` and `org?.is_active`.
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
export type UserType = "super_admin" | "central_admin";

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
```

### `src/lib/api.ts`

Bearer interceptor, queued refresh-on-401, logout when refresh fails.

```ts
import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";
import type { MeResponse, TokenPair } from "./types";

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
```

Skip the interceptor refresh for `/api/auth/token/refresh/` itself (the snippet
uses a bare `axios.post` for that reason).

### Route guard

```tsx
import { Navigate, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { getMe, getTokens } from "./lib/api";
import type { MeResponse } from "./lib/types";

export function RequireAuth({ orgOnly = false }: { orgOnly?: boolean }) {
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

  if (orgOnly) {
    if (me.profile?.user_type !== "central_admin") {
      return <Navigate to="/admin-home" replace />;
    }
    if (!me.org?.is_active) {
      return <p>Your organisation has been suspended.</p>;
    }
  }

  return <Outlet context={{ me }} />;
}
```

- Unauthenticated → `/login`
- `central_admin` + inactive org → show suspended, do not render org UI
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
