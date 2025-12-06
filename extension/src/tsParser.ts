import * as vscode from 'vscode';
import * as path from 'path';
import Parser from 'web-tree-sitter';

type LoadedGrammars = {
  python?: Parser.Language;
  typescript?: Parser.Language;
  tsx?: Parser.Language;
  javascript?: Parser.Language;
};

type GrammarSummary = {
  python: boolean;
  typescript: boolean;
  tsx: boolean;
  javascript: boolean;
  initFailed: boolean;
};

let initOnce: Promise<LoadedGrammars> | null = null; // Reset for new WASM files
let grammarSummary: GrammarSummary = {
  python: false,
  typescript: false,
  tsx: false,
  javascript: false,
  initFailed: false
};

export async function loadGrammarsOnce(context: vscode.ExtensionContext, outputChannel?: vscode.OutputChannel): Promise<LoadedGrammars> {
  if (initOnce) {
    outputChannel?.appendLine('Tree-sitter: returning cached grammars');
    return initOnce;
  }
  
  outputChannel?.appendLine('Tree-sitter: starting initialization...');
  
  initOnce = (async () => {
    try {
      outputChannel?.appendLine('Tree-sitter: initializing WASM runtime...');
      
      // Try alternative initialization for VS Code extension environment
      const wasmPath = context.asAbsolutePath(path.join('node_modules', 'web-tree-sitter', 'tree-sitter.wasm'));
      outputChannel?.appendLine(`Tree-sitter: WASM path: ${wasmPath}`);
      
      // Initialize with explicit WASM path
      await Parser.init({
        locateFile(scriptName: string, scriptDirectory: string) {
          outputChannel?.appendLine(`Tree-sitter: locateFile called: ${scriptName} in ${scriptDirectory}`);
          if (scriptName === 'tree-sitter.wasm') {
            return wasmPath;
          }
          return path.join(scriptDirectory, scriptName);
        }
      });
      
      outputChannel?.appendLine('Tree-sitter: WASM runtime initialized successfully');
      
      const base = context.asAbsolutePath('parsers');
      outputChannel?.appendLine(`Tree-sitter: parser base path: ${base}`);
      
      outputChannel?.appendLine('Tree-sitter: loading language grammars...');
      
      // Load grammars one by one with individual error handling
      const grammars: LoadedGrammars = {};
      
      // Python grammar
      try {
        outputChannel?.appendLine('Loading python.wasm...');
        grammars.python = await Parser.Language.load(path.join(base, 'python.wasm'));
        grammarSummary.python = true;
        outputChannel?.appendLine('Tree-sitter: python grammar loaded ✓');
      } catch (error) {
        outputChannel?.appendLine(`Tree-sitter: python grammar failed: ${error}`);
      }
      
      // TypeScript grammar
      try {
        outputChannel?.appendLine('Loading typescript.wasm...');
        grammars.typescript = await Parser.Language.load(path.join(base, 'typescript.wasm'));
        grammarSummary.typescript = true;
        outputChannel?.appendLine('Tree-sitter: typescript grammar loaded ✓');
      } catch (error) {
        outputChannel?.appendLine(`Tree-sitter: typescript grammar failed: ${error}`);
      }
      
      // TSX grammar
      try {
        outputChannel?.appendLine('Loading tsx.wasm...');
        grammars.tsx = await Parser.Language.load(path.join(base, 'tsx.wasm'));
        grammarSummary.tsx = true;
        outputChannel?.appendLine('Tree-sitter: tsx grammar loaded ✓');
      } catch (error) {
        outputChannel?.appendLine(`Tree-sitter: tsx grammar failed: ${error}`);
      }
      
      // JavaScript grammar
      try {
        outputChannel?.appendLine('Loading javascript.wasm...');
        grammars.javascript = await Parser.Language.load(path.join(base, 'javascript.wasm'));
        grammarSummary.javascript = true;
        outputChannel?.appendLine('Tree-sitter: javascript grammar loaded ✓');
      } catch (error) {
        outputChannel?.appendLine(`Tree-sitter: javascript grammar failed: ${error}`);
      }
      
      outputChannel?.appendLine('Tree-sitter: initialization complete');
      return grammars;
    } catch (error) {
      outputChannel?.appendLine(`Tree-sitter: initialization failed with error: ${error}`);
      grammarSummary.initFailed = true;
      throw error;
    }
  })();
  
  return initOnce;
}

export function getLoadedGrammarsSummary(): GrammarSummary {
  return { ...grammarSummary };
}

export function resetGrammarCache(): void {
  initOnce = null;
  grammarSummary = {
    python: false,
    typescript: false,
    tsx: false,
    javascript: false,
    initFailed: false
  };
}