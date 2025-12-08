import * as vscode from "vscode";

// Extension version - updated on each release
const EXTENSION_VERSION = "0.0.1";

// Secret storage reference - set during extension activation
let secretStorage: vscode.SecretStorage | undefined;

/**
 * Initialize the HTTP module with the extension context.
 * Must be called during extension activation.
 */
export function initHttp(context: vscode.ExtensionContext): void {
  secretStorage = context.secrets;
}

const BASE = () => vscode.workspace.getConfiguration("aspectcode").get<string>("serverBaseUrl") ?? "http://localhost:8000";
const CONFIG_API_KEY = () => vscode.workspace.getConfiguration("aspectcode").get<string>("apiKey") ?? "";

/**
 * Get the API key, preferring SecretStorage over config.
 */
async function getApiKey(): Promise<string> {
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
 * Build common headers for all requests including auth
 */
async function getHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-AspectCode-Client-Version": EXTENSION_VERSION,
  };
  
  const apiKey = await getApiKey();
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }
  
  return headers;
}

/**
 * Handle HTTP errors with user-friendly messages
 */
function handleHttpError(status: number, statusText: string): never {
  if (status === 401) {
    vscode.window.showErrorMessage(
      "Aspect Code: API key is missing or invalid. Set 'aspectcode.apiKey' in your VS Code settings.",
      "Open Settings"
    ).then(choice => {
      if (choice === "Open Settings") {
        vscode.commands.executeCommand("workbench.action.openSettings", "aspectcode.apiKey");
      }
    });
    throw new Error("Authentication failed: Invalid or missing API key");
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
    const res = await fetch(`${BASE()}${path}`, { 
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
    const res = await fetch(`${BASE()}${path}`, { 
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
