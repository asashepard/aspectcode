/**
 * LLM Client Module
 * 
 * Provides a provider-agnostic abstraction for LLM API calls.
 * Routes requests through the Aspect Code backend to avoid exposing API keys.
 */

import * as vscode from 'vscode';

export interface LlmRequest {
  systemPrompt?: string;
  userPrompt: string;
  maxTokens?: number;
}

export interface LlmResponse {
  text: string;
}

export interface LlmClient {
  isConfigured(): Promise<boolean>;
  complete(request: LlmRequest): Promise<LlmResponse>;
}

/**
 * Backend-proxied LLM client implementation.
 * Routes requests through Aspect Code server which holds the API key.
 */
class BackendLlmClient implements LlmClient {
  constructor(
    private outputChannel?: vscode.OutputChannel
  ) {}

  async isConfigured(): Promise<boolean> {
    // Check if backend is available and LLM is configured
    const config = vscode.workspace.getConfiguration('Aspect Code');
    const serverUrl = config.get<string>('serverBaseUrl', 'http://localhost:8000');
    
    try {
      const response = await fetch(`${serverUrl}/health`);
      if (!response.ok) {
        this.outputChannel?.appendLine('[LLM] Backend not available');
        return false;
      }
      
      const health = await response.json();
      this.outputChannel?.appendLine(`[LLM] Backend health: ${JSON.stringify(health)}`);
      
      // Backend is available - LLM config is handled server-side
      return true;
    } catch (error) {
      this.outputChannel?.appendLine(`[LLM] Backend check failed: ${error}`);
      return false;
    }
  }

  async complete(request: LlmRequest): Promise<LlmResponse> {
    const config = vscode.workspace.getConfiguration('Aspect Code');
    const serverUrl = config.get<string>('serverBaseUrl', 'http://localhost:8000');
    const endpoint = `${serverUrl}/llm/complete`;

    this.outputChannel?.appendLine(`[LLM] Calling backend proxy at ${endpoint}`);

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          systemPrompt: request.systemPrompt,
          userPrompt: request.userPrompt,
          maxTokens: request.maxTokens || 2000
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        this.outputChannel?.appendLine(`[LLM] Backend error: ${response.status} ${errorText}`);
        
        if (response.status === 503) {
          throw new Error('LLM service not configured on server. Set ASPECT_CODE_LLM_API_KEY environment variable.');
        }
        
        throw new Error(`LLM request failed: ${response.status} - ${errorText}`);
      }

      const data: any = await response.json();
      
      if (!data.text) {
        throw new Error('Backend returned no text');
      }

      this.outputChannel?.appendLine(`[LLM] Response received: ${data.text.length} chars`);

      return { text: data.text };

    } catch (error) {
      this.outputChannel?.appendLine(`[LLM] Exception: ${error}`);
      throw error;
    }
  }
}

/**
 * No-op LLM client that always reports as not configured
 */
class NoopLlmClient implements LlmClient {
  async isConfigured(): Promise<boolean> {
    return false;
  }

  async complete(request: LlmRequest): Promise<LlmResponse> {
    throw new Error('LLM client not configured');
  }
}

/**
 * Factory function to create the appropriate LLM client based on configuration
 */
export function createLlmClient(
  context: vscode.ExtensionContext,
  outputChannel?: vscode.OutputChannel
): LlmClient {
  // Always use backend proxy now (no more direct API calls)
  return new BackendLlmClient(outputChannel);
}

