import axios, { AxiosError, type AxiosInstance } from "axios";

/**
 * Written as literal `process.env.NEXT_PUBLIC_*` reads so Next.js can
 * substitute them into the browser bundle at build time.
 */
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const CFO_API_URL = process.env.NEXT_PUBLIC_CFO_API_URL || API_URL;

/**
 * Clients are built once at module load rather than per request, so each one
 * keeps a single connection pool and header set.
 *
 * The reviewer header marks an intentional local operation. It is not
 * authentication, and these services are expected to stay on loopback.
 */
function createApiClient(baseURL: string): AxiosInstance {
  return axios.create({
    baseURL,
    withCredentials: true,
    headers: {
      "Content-Type": "application/json",
      "X-SchoolTrace-Reviewer": "local-reviewer",
      // These responses describe live state; a cached one would be misleading.
      "Cache-Control": "no-cache",
    },
    // A hung request should surface as an error, not a spinner forever.
    timeout: 20_000,
  });
}

export const api = createApiClient(API_URL);
export const cfoApi = createApiClient(CFO_API_URL);

/** FastAPI reports problems in `detail`, as a string, a list of errors, or an object. */
function readDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => (typeof e === "object" && e && "msg" in e ? String((e as { msg: unknown }).msg) : String(e)))
      .join("; ");
  }
  if (typeof detail === "object" && detail && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return null;
}

/** Turns a request failure into a message worth showing someone. */
export function describeApiError(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return error instanceof Error ? error.message : "Something went wrong.";
  }

  const axiosError = error as AxiosError<{ detail?: unknown }>;
  const detail = readDetail(axiosError.response?.data?.detail);
  if (detail) return detail;

  if (axiosError.code === "ECONNABORTED") return "The records service timed out.";
  if (!axiosError.response) return "The records service is not reachable.";
  return `Records service returned ${axiosError.response.status}.`;
}

/**
 * A failed request, carrying the HTTP status when there was a response.
 *
 * Callers need the status to tell "nothing there yet" (404) apart from a real
 * failure, and a plain Error would have thrown that away.
 */
export class ApiError extends Error {
  readonly status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** True when the caller aborted, which is a cancelled request rather than a failure. */
export function isAbort(error: unknown): boolean {
  return axios.isCancel(error) || (axios.isAxiosError(error) && error.code === "ERR_CANCELED");
}

export interface RequestOptions {
  method?: string;
  /** A plain value; the client serialises it. Do not pre-stringify. */
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

async function request<T>(client: AxiosInstance, path: string, options: RequestOptions): Promise<T> {
  // A multipart upload needs the boundary that the browser generates, so the
  // JSON default must be cleared rather than overridden.
  const isForm = typeof FormData !== "undefined" && options.body instanceof FormData;
  const headers = { ...options.headers, ...(isForm ? { "Content-Type": undefined } : {}) };

  try {
    const response = await client.request<T>({
      url: path,
      method: options.method ?? "GET",
      data: options.body,
      headers,
      signal: options.signal,
    });
    return response.data;
  } catch (error) {
    if (isAbort(error)) throw error;
    const status = axios.isAxiosError(error) ? error.response?.status : undefined;
    throw new ApiError(describeApiError(error), status);
  }
}

/** Response body from the intake API, or a thrown error carrying a readable message. */
export function intakeApi<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return request<T>(api, path, options);
}

/** Response body from the CFO investigation API. */
export function cfoRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return request<T>(cfoApi, path, options);
}

/** Like cfoRequest, but a 404 means "nothing yet" rather than an error. */
export async function cfoRequestOptional<T>(path: string, options: RequestOptions = {}): Promise<T | null> {
  try {
    return await request<T>(cfoApi, path, options);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
