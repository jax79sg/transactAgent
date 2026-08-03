import { apiBaseUrl } from "../config";
import type { ApiErrorBody } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: ApiErrorBody,
  ) {
    super(body.message);
  }
}

let currentToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

/** Called once by AuthContext at startup -- keeps this module decoupled from React. */
export function registerAuthHandlers(getToken: () => string | null, unauthorizedCallback: () => void): void {
  onUnauthorized = unauthorizedCallback;
  tokenGetter = getToken;
}

let tokenGetter: () => string | null = () => currentToken;

export function setToken(token: string | null): void {
  currentToken = token;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  // `unknown` rather than a narrower value type: callers pass filter-state objects
  // (TransactionFilterState, DashboardFilterState) whose fields are typed unions
  // (e.g. FlowDirection), not plain strings -- a Record<string, string | ...> value
  // type rejects those at the call site even though `String(value)` below handles
  // any of them fine at runtime.
  query?: Record<string, unknown>;
}

export function toSnakeCase(key: string): string {
  return key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}

/**
 * Unit 2's query parameters are snake_case (plain BaseModel / FastAPI Query params,
 * e.g. `date_from`, `page_size`) -- unlike its JSON request/response bodies, which
 * are camelCase (via the CamelModel base). Caught before ever running this against
 * the real API: every filter would have silently been ignored (FastAPI falling back
 * to defaults for unrecognized param names) had this conversion been missing.
 * Callers pass camelCase keys (idiomatic TS); this is the one place the conversion
 * happens.
 */
function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(path, apiBaseUrl);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== "") {
        url.searchParams.set(toSnakeCase(key), String(value));
      }
    }
  }
  return url.toString();
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = tokenGetter();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (response.status === 401) {
    onUnauthorized?.();
    const body = await response.json().catch(() => ({ error: "unauthorized", message: "Unauthorized" }));
    throw new ApiError(401, body);
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: "unknown", message: response.statusText }));
    throw new ApiError(response.status, body);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
