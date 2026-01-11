import * as vscode from "vscode";

// Extension version - read from package.json at activation
let extensionVersion = "0.0.0";

// Secret storage reference - set during extension activation
let secretStorage: vscode.SecretStorage | undefined;

export type ApiKeyAuthStatus = 'unknown' | 'ok' | 'invalid' | 'revoked';

let apiKeyAuthStatus: ApiKeyAuthStatus = 'unknown';
const apiKeyAuthStatusEmitter = new vscode.EventEmitter<ApiKeyAuthStatus>();
export const onDidChangeApiKeyAuthStatus = apiKeyAuthStatusEmitter.event;

export function getApiKeyAuthStatus(): ApiKeyAuthStatus {
  return apiKeyAuthStatus;
}

// Feature-gating helper: treat only explicit 'ok' as valid.
// 'unknown' is considered not valid until verified.
export function hasValidApiKey(): boolean {
  return apiKeyAuthStatus === 'ok';
}

// Treat invalid/revoked as hard-blocked until the user changes the key.
export function isApiKeyBlocked(): boolean {
  return apiKeyAuthStatus === 'invalid' || apiKeyAuthStatus === 'revoked';
}

// Async presence check (covers SecretStorage + config).
export async function hasApiKeyConfigured(): Promise<boolean> {
  const key = (await getApiKey()).trim();
  return key.length > 0;
}

export function resetApiKeyAuthStatus(): void {
  setApiKeyAuthStatus('unknown');
}

/**
 * Legacy-style HTTP error handler used by older call sites that only have
 * status/statusText (not the full Response).
 *
 * This updates API key auth status and throws.
 * Note: For 401/403, we only show error toasts if a key was actually configured
 * (to avoid spamming users in offline mode).
 */
export function handleHttpError(status: number, statusText: string): never {
  if (status === 401) {
    setApiKeyAuthStatus('invalid');
    // Only show error toast if user had configured a key (not in offline mode)
    // Check is async but we use cached apiKeyAuthStatus as proxy
    // If status was 'ok' before, user had a working key that's now invalid
    // Otherwise they never had a key configured
    hasApiKeyConfigured().then(hasKey => {
      if (hasKey) {
        void vscode.window.showErrorMessage(
          'Aspect Code: API key is invalid.',
          'Enter API Key'
        ).then(choice => {
          if (choice === 'Enter API Key') {
            void vscode.commands.executeCommand('aspectcode.enterApiKey');
          }
        });
      }
    });
    throw new Error('Authentication failed: Invalid or missing API key');
  }

  if (status === 403) {
    setApiKeyAuthStatus('revoked');
    void vscode.window.showErrorMessage(
      'Aspect Code: Your API key has been revoked.',
      'Enter New API Key'
    ).then(choice => {
      if (choice === 'Enter New API Key') {
        void vscode.commands.executeCommand('aspectcode.enterApiKey');
      }
    });
    throw new Error('Authentication failed: API key revoked');
  }

  if (status === 426) {
    void vscode.window.showErrorMessage(
      'Aspect Code: Extension version too old. Please update.',
      'Check for Updates'
    ).then(choice => {
      if (choice === 'Check for Updates') {
        void vscode.commands.executeCommand('workbench.extensions.action.checkForUpdates');
      }
    });
    throw new Error('Client version too old');
  }

  throw new Error(`HTTP ${status}: ${statusText || 'Request failed'}`);
}

function setApiKeyAuthStatus(next: ApiKeyAuthStatus): void {
  if (apiKeyAuthStatus === next) return;
  apiKeyAuthStatus = next;
  apiKeyAuthStatusEmitter.fire(next);
}

// --- Network Event Tracking (for debug info) ---

interface NetworkEvent {
  timestamp: number;
  endpoint: string;
  method: string;
  status: number;
  durationMs: number;
  requestId?: string;
  error?: string;
  rateLimitReason?: string;
}

const networkEvents: NetworkEvent[] = [];
const MAX_NETWORK_EVENTS = 20;

function recordNetworkEvent(event: NetworkEvent): void {
  networkEvents.push(event);
  if (networkEvents.length > MAX_NETWORK_EVENTS) {
    networkEvents.shift();
  }
}

export function getNetworkEvents(): NetworkEvent[] {
  return [...networkEvents];
}

// --- Backoff Configuration ---

const BACKOFF_BASE_MS = 500;
const BACKOFF_MAX_MS = 10000;
const MAX_RETRIES = 3;

function getJitter(maxMs: number): number {
  return Math.random() * maxMs;
}

function calculateBackoff(attempt: number, retryAfterSecs?: number): number {
  if (retryAfterSecs !== undefined && retryAfterSecs > 0) {
    // Respect Retry-After header, but cap at 60 seconds
    return Math.min(retryAfterSecs * 1000, 60000);
  }
  // Exponential backoff with jitter
  const exponential = Math.min(BACKOFF_BASE_MS * Math.pow(2, attempt), BACKOFF_MAX_MS);
  return exponential + getJitter(exponential * 0.2);
}

// --- Rate Limit Response Types ---

interface RateLimitError {
  error: 'rate_limited';
  reason: 'rpm' | 'concurrency' | 'daily_cap';
  retry_after_seconds: number;
  request_id?: string;
  daily_cap?: number;
  used_today?: number;
  reset_at_utc?: string;
}

function isRateLimitError(body: any): body is RateLimitError {
  return body && body.error === 'rate_limited';
}

/**
 * Initialize the HTTP module with the extension context.
 * Must be called during extension activation.
 */
export function initHttp(context: vscode.ExtensionContext): void {
  secretStorage = context.secrets;
  extensionVersion = context.extension.packageJSON.version ?? "0.0.0";
}

export function getExtensionVersion(): string {
  return extensionVersion;
}

/**
 * Get the canonical base URL for the Aspect Code server.
 */
export function getBaseUrl(): string {
  const config = vscode.workspace.getConfiguration("aspectcode");
  return config.get<string>("serverBaseUrl")
    || config.get<string>("apiUrl")
    || "https://api.aspectcode.com";
}

const CONFIG_API_KEY = () => vscode.workspace.getConfiguration("aspectcode").get<string>("apiKey") ?? "";

/**
 * Get the API key, preferring SecretStorage over config.
 */
export async function getApiKey(): Promise<string> {
  if (secretStorage) {
    const secretKey = await secretStorage.get('aspectcode.apiKey');
    if (secretKey) {
      return secretKey;
    }
  }
  return CONFIG_API_KEY();
}

/**
 * Build common headers for all requests including auth.
 */
export async function getHeaders(requestId?: string): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-AspectCode-Client-Version": extensionVersion,
  };
  
  if (requestId) {
    headers["X-Request-Id"] = requestId;
  }
  
  const apiKey = await getApiKey();
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }
  
  return headers;
}

/**
 * Handle HTTP errors with user-friendly messages.
 * Returns retry info for retryable errors, throws for non-retryable.
 * Note: For 401/403, we only show error toasts if a key was actually configured
 * (to avoid spamming users in offline mode).
 */
async function handleHttpResponseError(
  res: Response,
  endpoint: string,
  requestId: string
): Promise<{ shouldRetry: boolean; retryAfterSecs?: number; isDailyCap?: boolean }> {
  const status = res.status;
  
  if (status === 401) {
    setApiKeyAuthStatus('invalid');
    // Only show error if user had configured a key (not in offline mode)
    const hasKey = await hasApiKeyConfigured();
    if (hasKey) {
      vscode.window.showErrorMessage(
        "Aspect Code: API key is invalid.",
        "Enter API Key"
      ).then(choice => {
        if (choice === "Enter API Key") {
          vscode.commands.executeCommand("aspectcode.enterApiKey");
        }
      });
    }
    throw new Error("Authentication failed: Invalid or missing API key");
  }
  
  if (status === 403) {
    setApiKeyAuthStatus('revoked');
    vscode.window.showErrorMessage(
      "Aspect Code: Your API key has been revoked.",
      "Enter New API Key"
    ).then(choice => {
      if (choice === "Enter New API Key") {
        vscode.commands.executeCommand("aspectcode.enterApiKey");
      }
    });
    throw new Error("Authentication failed: API key revoked");
  }
  
  if (status === 426) {
    vscode.window.showErrorMessage(
      "Aspect Code: Extension version too old. Please update.",
      "Check for Updates"
    ).then(choice => {
      if (choice === "Check for Updates") {
        vscode.commands.executeCommand("workbench.extensions.action.checkForUpdates");
      }
    });
    throw new Error("Client version too old");
  }
  
  if (status === 429) {
    try {
      const body = await res.json();
      if (isRateLimitError(body)) {
        const retryAfterSecs = body.retry_after_seconds || parseInt(res.headers.get("Retry-After") || "5", 10);
        
        // Daily cap is NOT retryable automatically
        if (body.reason === 'daily_cap') {
          const resetTime = body.reset_at_utc ? new Date(body.reset_at_utc).toLocaleTimeString() : "midnight UTC";
          vscode.window.showWarningMessage(
            `Aspect Code: Daily limit reached (${body.used_today}/${body.daily_cap}). Resets at ${resetTime}.`
          );
          return { shouldRetry: false, isDailyCap: true };
        }
        
        // RPM and concurrency are retryable
        return { shouldRetry: true, retryAfterSecs };
      }
    } catch {
      // Fallback if body parsing fails
    }
    const retryAfter = parseInt(res.headers.get("Retry-After") || "5", 10);
    return { shouldRetry: true, retryAfterSecs: retryAfter };
  }
  
  if (status === 503) {
    // Service unavailable - retryable
    const retryAfter = parseInt(res.headers.get("Retry-After") || "5", 10);
    return { shouldRetry: true, retryAfterSecs: retryAfter };
  }
  
  // Other errors are not retryable
  throw new Error(`HTTP ${status}: ${res.statusText}`);
}

/**
 * Make a request with automatic retry for 429/503.
 */
async function fetchWithRetry<T>(
  method: 'GET' | 'POST',
  path: string,
  body?: any,
  timeoutMs: number = 30000
): Promise<T> {
  const requestId = crypto.randomUUID();
  const startTime = Date.now();
  let lastError: Error | null = null;
  
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    
    try {
      const headers = await getHeaders(requestId);
      const res = await fetch(`${getBaseUrl()}${path}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      
      const durationMs = Date.now() - startTime;
      const responseRequestId = res.headers.get("X-Request-Id") || requestId;
      
      if (res.ok) {
        setApiKeyAuthStatus('ok');
        recordNetworkEvent({
          timestamp: Date.now(),
          endpoint: path,
          method,
          status: res.status,
          durationMs,
          requestId: responseRequestId,
        });
        return res.json() as Promise<T>;
      }
      
      // Handle error
      const { shouldRetry, retryAfterSecs, isDailyCap } = await handleHttpResponseError(res, path, requestId);
      
      recordNetworkEvent({
        timestamp: Date.now(),
        endpoint: path,
        method,
        status: res.status,
        durationMs,
        requestId: responseRequestId,
        rateLimitReason: isDailyCap ? 'daily_cap' : (res.status === 429 ? 'rpm_or_concurrency' : undefined),
      });
      
      if (!shouldRetry || attempt >= MAX_RETRIES) {
        if (isDailyCap) {
          throw new Error("Daily limit reached. Try again tomorrow.");
        }
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      
      // Calculate backoff and wait
      const backoffMs = calculateBackoff(attempt, retryAfterSecs);
      const backoffSecs = Math.ceil(backoffMs / 1000);
      
      // Show status bar message during retry wait
      vscode.window.setStatusBarMessage(`$(sync~spin) Aspect Code: Rate limited, retrying in ${backoffSecs}s...`, backoffMs);
      
      await new Promise(resolve => setTimeout(resolve, backoffMs));
      
    } catch (error) {
      clearTimeout(timeoutId);
      
      const durationMs = Date.now() - startTime;
      const isAbort = error instanceof Error && error.name === 'AbortError';
      const isNetwork = error instanceof TypeError;
      
      recordNetworkEvent({
        timestamp: Date.now(),
        endpoint: path,
        method,
        status: isAbort ? 0 : -1,
        durationMs,
        requestId,
        error: isAbort ? 'timeout' : (isNetwork ? 'network_error' : String(error)),
      });
      
      // Network errors are retryable
      if ((isNetwork || isAbort) && attempt < MAX_RETRIES) {
        const backoffMs = calculateBackoff(attempt);
        await new Promise(resolve => setTimeout(resolve, backoffMs));
        lastError = error instanceof Error ? error : new Error(String(error));
        continue;
      }
      
      throw error;
    }
  }
  
  throw lastError || new Error("Request failed after retries");
}

export async function post<T>(path: string, body: any): Promise<T> {
  return fetchWithRetry<T>('POST', path, body, 30000);
}

export async function get<T>(path: string): Promise<T> {
  return fetchWithRetry<T>('GET', path, undefined, 5000);
}

// --- Single-Flight Requests ---

const inFlightRequests = new Map<string, Promise<any>>();

/**
 * Make a request that's deduplicated per key.
 * If a request with the same key is already in flight, returns that promise.
 */
export async function singleFlight<T>(
  key: string,
  requestFn: () => Promise<T>
): Promise<T> {
  const existing = inFlightRequests.get(key);
  if (existing) {
    return existing as Promise<T>;
  }
  
  const promise = requestFn().finally(() => {
    inFlightRequests.delete(key);
  });
  
  inFlightRequests.set(key, promise);
  return promise;
}

/**
 * Check if a request is currently in flight.
 */
export function isRequestInFlight(key: string): boolean {
  return inFlightRequests.has(key);
}

/**
 * Cancel tracking for an in-flight request (doesn't cancel the actual request).
 */
export function clearInFlightRequest(key: string): void {
  inFlightRequests.delete(key);
}

// Import types from state
import type { Capabilities } from "./state";

export async function fetchCapabilities(): Promise<Capabilities> {
  try {
    return await get<Capabilities>("/patchlets/capabilities");
  } catch (error) {
    console.warn('[Aspect Code] Failed to fetch capabilities:', error);
    return {
      language: 'python',
      fixable_rules: []
    };
  }
}
