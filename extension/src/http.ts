import * as vscode from "vscode";

// Extension version - read from package.json at activation
let extensionVersion = "0.0.0";

// Secret storage reference - set during extension activation
let secretStorage: vscode.SecretStorage | undefined;

/**
 * Initialize the HTTP module with the extension context.
 * Must be called during extension activation.
 */
export function initHttp(context: vscode.ExtensionContext): void {
  secretStorage = context.secrets;
  // Read version from extension manifest (package.json)
  extensionVersion = context.extension.packageJSON.version ?? "0.0.0";
}

/**
 * Get the canonical base URL for the Aspect Code server.
 * Checks serverBaseUrl first (preferred), then apiUrl (legacy), then default.
 * Exported so all call sites can use a single source of truth.
 */
export function getBaseUrl(): string {
  const config = vscode.workspace.getConfiguration("aspectcode");
  // Prefer serverBaseUrl (canonical), fall back to apiUrl (legacy), then default
  return config.get<string>("serverBaseUrl")
    || config.get<string>("apiUrl")
    || "https://api.aspectcode.com";
}

const CONFIG_API_KEY = () => vscode.workspace.getConfiguration("aspectcode").get<string>("apiKey") ?? "";

/**
 * Get the API key, preferring SecretStorage over config.
 */
export async function getApiKey(): Promise<string> {
  // First, try SecretStorage (alpha registration)
  if (secretStorage) {
    const secretKey = await secretStorage.get('aspectcode.apiKey');
    if (secretKey) {
      return secretKey;
    }
  }
  
  // Fall back to config setting (for testing or manual setup)
  return CONFIG_API_KEY();
}

/**
 * Build common headers for all requests including auth.
 * Exported for use by direct fetch calls that can't use post()/get().
 */
export async function getHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-AspectCode-Client-Version": extensionVersion,
  };
  
  const apiKey = await getApiKey();
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }
  
  return headers;
}

/**
 * Handle HTTP errors with user-friendly messages.
 * Exported for use by direct fetch calls.
 */
export function handleHttpError(status: number, statusText: string): never {
  if (status === 401) {
    vscode.window.showErrorMessage(
      "Aspect Code: API key is missing or invalid. Please enter a valid API key.",
      "Enter API Key"
    ).then(choice => {
      if (choice === "Enter API Key") {
        vscode.commands.executeCommand("aspectcode.enterApiKey");
      }
    });
    throw new Error("Authentication failed: Invalid or missing API key");
  }
  
  if (status === 403) {
    vscode.window.showErrorMessage(
      "Aspect Code: Your API key has been revoked. Please contact support for a new key.",
      "Enter New API Key"
    ).then(choice => {
      if (choice === "Enter New API Key") {
        vscode.commands.executeCommand("aspectcode.enterApiKey");
      }
    });
    throw new Error("Authentication failed: API key has been revoked");
  }
  
  if (status === 426) {
    vscode.window.showErrorMessage(
      "Aspect Code: Your extension version is too old. Please update the Aspect Code extension.",
      "Check for Updates"
    ).then(choice => {
      if (choice === "Check for Updates") {
        vscode.commands.executeCommand("workbench.extensions.action.checkForUpdates");
      }
    });
    throw new Error("Client version too old: Please update the extension");
  }
  
  if (status === 429) {
    vscode.window.showWarningMessage(
      "Aspect Code: Rate limit exceeded. Please wait a moment before trying again."
    );
    throw new Error("Rate limit exceeded");
  }
  
  throw new Error(`${status} ${statusText}`);
}

export async function post<T>(path: string, body: any): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout for validation
  
  try {
    const headers = await getHeaders();
    const res = await fetch(`${getBaseUrl()}${path}`, { 
      method: "POST", 
      headers, 
      body: JSON.stringify(body),
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    
    if (!res.ok) {
      handleHttpError(res.status, res.statusText);
    }
    return res.json() as Promise<T>;
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
}

export async function get<T>(path: string): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout
  
  try {
    const headers = await getHeaders();
    const res = await fetch(`${getBaseUrl()}${path}`, { 
      method: "GET", 
      headers,
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    
    if (!res.ok) {
      handleHttpError(res.status, res.statusText);
    }
    return res.json() as Promise<T>;
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
}

// Import types from state
import type { Capabilities } from "./state";

export async function fetchCapabilities(): Promise<Capabilities> {
  try {
    return await get<Capabilities>("/patchlets/capabilities");
  } catch (error) {
    console.warn('[Aspect Code] Failed to fetch capabilities:', error);
    // Return default capabilities if endpoint doesn't exist
    return {
      language: 'python',
      fixable_rules: []
    };
  }
}
