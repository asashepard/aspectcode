import * as vscode from "vscode";

const BASE = () => vscode.workspace.getConfiguration("Aspect Code").get<string>("serverBaseUrl") ?? "http://localhost:8000";

export async function post<T>(path: string, body: any): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout for validation
  
  try {
    const res = await fetch(`${BASE()}${path}`, { 
      method: "POST", 
      headers: { "Content-Type": "application/json" }, 
      body: JSON.stringify(body),
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    
    if (!res.ok) {
      throw new Error(`${res.status} ${res.statusText}`);
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
    const res = await fetch(`${BASE()}${path}`, { 
      method: "GET", 
      headers: { "Content-Type": "application/json" },
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    
    if (!res.ok) {
      throw new Error(`${res.status} ${res.statusText}`);
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
