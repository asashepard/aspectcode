/**
 * Production-ready dependency analyzer for code relationships
 * Performs actual static analysis of imports, requires, and function calls
 * 
 * Optimized with pre-built indexes for O(1) lookups instead of O(N) scans.
 */

import * as vscode from 'vscode';
import * as path from 'path';

export interface DependencyLink {
  source: string;
  target: string;
  type: 'import' | 'export' | 'call' | 'inherit' | 'circular';
  strength: number;
  symbols: string[];  // What symbols are imported/called
  lines: number[];    // Line numbers where dependency occurs
  bidirectional: boolean;
}

export interface ImportStatement {
  module: string;
  symbols: string[];
  isDefault: boolean;
  line: number;
  raw: string;
}

export interface CallSite {
  callee: string;
  line: number;
  isExternal: boolean;  // Call to external module
}

/** Progress callback for dependency analysis */
export type DependencyProgressCallback = (current: number, total: number, phase: string) => void;

/**
 * Pre-built indexes for fast module resolution.
 * Built once per analysis run; lookups are O(1) average.
 */
interface FileIndex {
  /** basename (no ext) -> list of full paths */
  byBasename: Map<string, string[]>;
  /** normalized lowercase path -> original path */
  byNormalizedPath: Map<string, string>;
  /** Set of all normalized lowercase paths for O(1) existence check */
  normalizedPathSet: Set<string>;
  /** For package-style imports: "pkg/subpkg/module" -> full path */
  byPackagePath: Map<string, string[]>;
}

export class DependencyAnalyzer {
  private workspaceFiles: Map<string, string> = new Map(); // file path -> content cache
  private fileIndex: FileIndex | null = null;
  
  /**
   * Set pre-loaded file contents to avoid redundant file reads.
   * Call this before analyzeDependencies if you already have the content.
   */
  setFileContentsCache(cache: Map<string, string>): void {
    this.workspaceFiles = new Map(cache);
  }
  
  /**
   * Build indexes for fast lookups. O(N) once, then O(1) per lookup.
   */
  private buildFileIndex(files: string[]): FileIndex {
    const byBasename = new Map<string, string[]>();
    const byNormalizedPath = new Map<string, string>();
    const normalizedPathSet = new Set<string>();
    const byPackagePath = new Map<string, string[]>();
    
    for (const file of files) {
      const normalized = path.normalize(file);
      const normalizedLower = normalized.toLowerCase();
      const basename = path.basename(file, path.extname(file));
      
      // Index by basename
      const basenameKey = basename.toLowerCase();
      if (!byBasename.has(basenameKey)) {
        byBasename.set(basenameKey, []);
      }
      byBasename.get(basenameKey)!.push(file);
      
      // Index by normalized path
      byNormalizedPath.set(normalizedLower, file);
      normalizedPathSet.add(normalizedLower);
      
      // Index by package-style path segments
      const parts = normalized.replace(/\\/g, '/').split('/');
      const basenameNoExt = path.basename(file, path.extname(file));
      for (let i = 0; i < parts.length - 1; i++) {
        const pkgPath = parts.slice(i, -1).join('/') + '/' + basenameNoExt;
        const pkgKey = pkgPath.toLowerCase();
        if (!byPackagePath.has(pkgKey)) {
          byPackagePath.set(pkgKey, []);
        }
        byPackagePath.get(pkgKey)!.push(file);
      }
    }
    
    return { byBasename, byNormalizedPath, normalizedPathSet, byPackagePath };
  }
  
  /**
   * Analyze all real dependencies between workspace files
   * @param files - List of file paths to analyze
   * @param onProgress - Optional callback for progress reporting
   */
  async analyzeDependencies(
    files: string[],
    onProgress?: DependencyProgressCallback
  ): Promise<DependencyLink[]> {
    const links: DependencyLink[] = [];
    const linkIndex = new Map<string, DependencyLink>();
    const startTime = Date.now();
    
    // Load and cache file contents (parallelized for performance)
    // Skip if cache was already set via setFileContentsCache
    if (this.workspaceFiles.size === 0) {
      onProgress?.(0, files.length, 'Loading file contents...');
      await this.loadFileContents(files, onProgress);
    }
    // Build indexes for fast resolution (O(N) once)
    onProgress?.(0, files.length, 'Building file index...');
    this.fileIndex = this.buildFileIndex(files);
    
    // Analyze each file
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      
      // Report progress every 10 files or on first/last
      if (i % 10 === 0 || i === files.length - 1) {
        onProgress?.(i + 1, files.length, `Analyzing imports (${i + 1}/${files.length})...`);
      }
      
      const fileDependencies = await this.analyzeFileImports(file);
      const fileCalls = await this.analyzeFileCalls(file);
      
      // Convert imports to dependency links
      for (const imp of fileDependencies) {
        const resolvedTarget = this.resolveModulePathFast(imp.module, file);
        
        // Skip self-references (file importing itself)
        if (resolvedTarget && resolvedTarget !== file) {
          const key = `import|${file}|${resolvedTarget}`;
          const existing = linkIndex.get(key);
          if (existing) {
            existing.symbols = [...new Set([...existing.symbols, ...imp.symbols])];
            existing.lines = [...new Set([...existing.lines, imp.line])].sort((a, b) => a - b);
            existing.strength = Math.min(1.0, Math.max(existing.strength, this.calculateImportStrength(imp)));
          } else {
            const link: DependencyLink = {
              source: file,
              target: resolvedTarget,
              type: 'import',
              strength: this.calculateImportStrength(imp),
              symbols: [...new Set(imp.symbols)],
              lines: [imp.line],
              bidirectional: false
            };
            links.push(link);
            linkIndex.set(key, link);
          }
        }
      }
      
      // Convert function calls to dependency links
      for (const call of fileCalls) {
        if (call.isExternal) {
          const resolvedTarget = this.resolveCallTargetFast(call.callee, file);
          // Skip self-references
          if (resolvedTarget && resolvedTarget !== file) {
            const callKey = `call|${file}|${resolvedTarget}`;
            const existing = linkIndex.get(callKey);
            
            if (existing) {
              if (!existing.symbols.includes(call.callee)) {
                existing.symbols.push(call.callee);
              }
              if (!existing.lines.includes(call.line)) {
                existing.lines.push(call.line);
              }
              existing.strength = Math.min(1.0, existing.strength + 0.1);
            } else {
              const link: DependencyLink = {
                source: file,
                target: resolvedTarget,
                type: 'call',
                strength: 0.6,
                symbols: [call.callee],
                lines: [call.line],
                bidirectional: false
              };
              links.push(link);
              linkIndex.set(callKey, link);
            }
          }
        }
      }
    }
    
    // Detect circular dependencies
    onProgress?.(files.length, files.length, 'Detecting circular dependencies...');
    this.detectCircularDependencies(links);
    
    // Merge bidirectional relationships
    this.mergeBidirectionalLinks(links);
    
    // Clear index after use to free memory
    this.fileIndex = null;
    
    // Sort links for deterministic output order
    return links.sort((a, b) => 
      a.source.localeCompare(b.source) || 
      a.target.localeCompare(b.target) ||
      a.type.localeCompare(b.type)
    );
  }

  /**
   * Analyze imports/requires in a single file
   */
  private async analyzeFileImports(filePath: string): Promise<ImportStatement[]> {
    const content = this.workspaceFiles.get(filePath);
    if (!content) return [];
    
    const extension = path.extname(filePath).toLowerCase();
    const lines = content.split('\n');
    const imports: ImportStatement[] = [];
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      const lineNum = i + 1;
      
      // Python imports
      if (extension === '.py') {
        const pythonImports = this.parsePythonImports(line, lineNum);
        imports.push(...pythonImports);
      }
      // TypeScript/JavaScript imports
      else if (['.ts', '.tsx', '.js', '.jsx', '.mjs'].includes(extension)) {
        const jsImports = this.parseJavaScriptImports(line, lineNum);
        imports.push(...jsImports);
      }
      // Java imports
      else if (extension === '.java') {
        const javaImports = this.parseJavaImports(line, lineNum);
        imports.push(...javaImports);
      }
      // C# using statements
      else if (extension === '.cs') {
        const csharpImports = this.parseCSharpImports(line, lineNum);
        imports.push(...csharpImports);
      }
      // Go imports
      else if (extension === '.go') {
        const goImports = this.parseGoImports(line, lineNum);
        imports.push(...goImports);
      }
    }
    
    return imports;
  }

  /**
   * Analyze function/method calls in a single file
   */
  private async analyzeFileCalls(filePath: string): Promise<CallSite[]> {
    const content = this.workspaceFiles.get(filePath);
    if (!content) return [];
    
    const extension = path.extname(filePath).toLowerCase();
    const lines = content.split('\n');
    const calls: CallSite[] = [];
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const lineNum = i + 1;
      
      // Look for function calls that might be external
      const callPattern = /(\w+\.)*(\w+)\s*\(/g;
      let match;
      
      while ((match = callPattern.exec(line)) !== null) {
        const fullCall = match[0];
        const callee = match[2];
        
        // Heuristics to detect external calls
        const isExternal = this.isLikelyExternalCall(fullCall, extension);
        
        if (isExternal) {
          calls.push({
            callee: callee,
            line: lineNum,
            isExternal: true
          });
        }
      }
    }
    
    return calls;
  }

  /**
   * Parse Python import statements
   */
  private parsePythonImports(line: string, lineNum: number): ImportStatement[] {
    const imports: ImportStatement[] = [];

    const cleanSymbol = (raw: string): string => {
      // Remove aliases and surrounding punctuation from multi-line imports.
      let s = raw.trim();
      // Drop inline comments.
      const hashIndex = s.indexOf('#');
      if (hashIndex >= 0) s = s.slice(0, hashIndex).trim();
      // Remove alias portion.
      s = s.split(' as ')[0].trim();
      // Strip common wrapper characters.
      s = s.replace(/^[({\[]+/, '').replace(/[)}\]]+$/, '').trim();
      // Remove trailing commas.
      s = s.replace(/,+$/, '').trim();
      return s;
    };

    const cleanSymbolsList = (symbolsStr: string): string[] => {
      return symbolsStr
        .split(',')
        .map(cleanSymbol)
        .filter((s) => s.length > 0)
        .filter((s) => s !== '(' && s !== ')' && s !== '[' && s !== ']' && s !== '{' && s !== '}');
    };
    
    // from module import symbols (including relative imports like `from .module` or `from ..pkg.mod`)
    const fromImportMatch = line.match(/from\s+(\.{0,3}[\w.]*?)\s+import\s+(.+)/);
    if (fromImportMatch) {
      let module = fromImportMatch[1];
      
      // Skip if module is empty (malformed)
      if (!module || module === '') {
        return imports;
      }
      const symbolsStr = fromImportMatch[2];
      const symbols = cleanSymbolsList(symbolsStr);
      
      // Handle package imports like "acme_shop.cycle_simple_b"
      // Extract the last part as the module name for resolution
      if (module.includes('.')) {
        const parts = module.split('.');
        // Try both full module path and just the last part
        imports.push({
          module: module, // Keep original for reference
          symbols,
          isDefault: false,
          line: lineNum,
          raw: line
        });
        
        // Also try just the last component for local imports
        const lastPart = parts[parts.length - 1];
        if (lastPart !== module) {
          imports.push({
            module: lastPart,
            symbols,
            isDefault: false,
            line: lineNum,
            raw: line
          });
        }
      } else {
        imports.push({
          module,
          symbols,
          isDefault: false,
          line: lineNum,
          raw: line
        });
      }

      // Important: don't also treat this as a plain "import ..." statement.
      // Otherwise lines like `from .settings import settings, DATABASE_URL` get mis-parsed
      // as importing a module named `settings` (the first imported symbol), creating bogus edges.
      return imports;
    }
    
    // import module
    // Skip lines that begin with `from ... import ...` (handled above).
    // Also skip if the word "import" doesn't begin the statement.
    if (!line.startsWith('from ')) {
      const importMatch = line.match(/^import\s+(.+)$/);
      if (importMatch) {
        const modulesStr = importMatch[1];
        const modules = cleanSymbolsList(modulesStr);
        for (const module of modules) {
          // Handle package imports
          if (module.includes('.')) {
            const parts = module.split('.');
            const lastPart = parts[parts.length - 1];
            
            imports.push({
              module: module,
              symbols: [module],
              isDefault: true,
              line: lineNum,
              raw: line
            });
            
            // Also try just the last component
            if (lastPart !== module) {
              imports.push({
                module: lastPart,
                symbols: [lastPart],
                isDefault: true,
                line: lineNum,
                raw: line
              });
            }
          } else {
            imports.push({
              module,
              symbols: [module],
              isDefault: true,
              line: lineNum,
              raw: line
            });
          }
        }
      }
    }
    
    return imports;
  }

  /**
   * Parse JavaScript/TypeScript import statements
   * Handles: named imports, default imports, namespace imports, side-effect imports,
   * type imports, mixed imports, re-exports, and require() calls.
   */
  private parseJavaScriptImports(line: string, lineNum: number): ImportStatement[] {
    const imports: ImportStatement[] = [];
    
    // Helper to extract module from quotes
    const extractModule = (str: string): string | null => {
      const match = str.match(/['"]([^'"]+)['"]/);
      return match ? match[1] : null;
    };
    
    // Helper to clean symbol names (remove 'as alias', 'type' prefix, whitespace)
    const cleanSymbols = (symbolsStr: string): string[] => {
      return symbolsStr
        .split(',')
        .map(s => s.trim())
        .map(s => s.replace(/^type\s+/, '')) // Remove 'type' prefix
        .map(s => s.split(/\s+as\s+/)[0].trim()) // Remove alias
        .filter(s => s.length > 0 && s !== 'type');
    };
    
    // Side-effect import: import 'module'
    const sideEffectMatch = line.match(/^\s*import\s+['"]([^'"]+)['"]\s*;?\s*$/);
    if (sideEffectMatch) {
      imports.push({
        module: sideEffectMatch[1],
        symbols: ['*'],
        isDefault: false,
        line: lineNum,
        raw: line
      });
      return imports;
    }
    
    // Re-exports: export { x } from 'module' or export * from 'module'
    const reExportNamedMatch = line.match(/^\s*export\s*\{\s*([^}]+)\s*\}\s*from\s*['"]([^'"]+)['"]/);
    if (reExportNamedMatch) {
      imports.push({
        module: reExportNamedMatch[2],
        symbols: cleanSymbols(reExportNamedMatch[1]),
        isDefault: false,
        line: lineNum,
        raw: line
      });
      return imports;
    }
    
    const reExportAllMatch = line.match(/^\s*export\s*\*\s*(?:as\s+\w+\s*)?from\s*['"]([^'"]+)['"]/);
    if (reExportAllMatch) {
      imports.push({
        module: reExportAllMatch[1],
        symbols: ['*'],
        isDefault: false,
        line: lineNum,
        raw: line
      });
      return imports;
    }
    
    // Combined import: import Default, { named } from 'module'
    // or: import Default, * as ns from 'module'
    const combinedMatch = line.match(/^\s*import\s+(?:type\s+)?(\w+)\s*,\s*(?:\{\s*([^}]+)\s*\}|\*\s*as\s+(\w+))\s*from\s*['"]([^'"]+)['"]/);
    if (combinedMatch) {
      const defaultSymbol = combinedMatch[1];
      const namedSymbols = combinedMatch[2] ? cleanSymbols(combinedMatch[2]) : [];
      const namespaceSymbol = combinedMatch[3];
      const module = combinedMatch[4];
      
      const allSymbols = [defaultSymbol, ...namedSymbols];
      if (namespaceSymbol) allSymbols.push(namespaceSymbol);
      
      imports.push({
        module,
        symbols: allSymbols,
        isDefault: true,
        line: lineNum,
        raw: line
      });
      return imports;
    }
    
    // Namespace import: import * as name from 'module'
    const namespaceMatch = line.match(/^\s*import\s+(?:type\s+)?\*\s*as\s+(\w+)\s*from\s*['"]([^'"]+)['"]/);
    if (namespaceMatch) {
      imports.push({
        module: namespaceMatch[2],
        symbols: [namespaceMatch[1]],
        isDefault: true,
        line: lineNum,
        raw: line
      });
      return imports;
    }
    
    // Named import: import { a, b as c } from 'module' (including import type)
    const namedImportMatch = line.match(/^\s*import\s+(?:type\s+)?\{\s*([^}]+)\s*\}\s*from\s*['"]([^'"]+)['"]/);
    if (namedImportMatch) {
      imports.push({
        module: namedImportMatch[2],
        symbols: cleanSymbols(namedImportMatch[1]),
        isDefault: false,
        line: lineNum,
        raw: line
      });
      return imports;
    }
    
    // Default import: import name from 'module' (including import type)
    const defaultImportMatch = line.match(/^\s*import\s+(?:type\s+)?(\w+)\s+from\s*['"]([^'"]+)['"]/);
    if (defaultImportMatch) {
      imports.push({
        module: defaultImportMatch[2],
        symbols: [defaultImportMatch[1]],
        isDefault: true,
        line: lineNum,
        raw: line
      });
      return imports;
    }
    
    // require() calls: const x = require('module') or const { a, b } = require('module')
    const requireMatch = line.match(/(?:const|let|var)\s+(?:\{\s*([^}]+)\s*\}|(\w+))\s*=\s*require\s*\(\s*['"]([^'"]+)['"]\s*\)/);
    if (requireMatch) {
      const symbols = requireMatch[1] ? cleanSymbols(requireMatch[1]) : [requireMatch[2]];
      imports.push({
        module: requireMatch[3],
        symbols,
        isDefault: !requireMatch[1],
        line: lineNum,
        raw: line
      });
      return imports;
    }
    
    // Dynamic import: import('module') - just detect the dependency
    const dynamicImportMatch = line.match(/import\s*\(\s*['"]([^'"]+)['"]\s*\)/);
    if (dynamicImportMatch) {
      imports.push({
        module: dynamicImportMatch[1],
        symbols: ['*'],
        isDefault: false,
        line: lineNum,
        raw: line
      });
    }
    
    return imports;
  }

  /**
   * Parse Java import statements
   */
  private parseJavaImports(line: string, lineNum: number): ImportStatement[] {
    const imports: ImportStatement[] = [];
    
    const importMatch = line.match(/import\s+(?:static\s+)?([\w.]+)(?:\.\*)?;/);
    if (importMatch) {
      const module = importMatch[1];
      const isWildcard = line.includes('.*');
      
      imports.push({
        module,
        symbols: isWildcard ? ['*'] : [module.split('.').pop() || module],
        isDefault: !isWildcard,
        line: lineNum,
        raw: line
      });
    }
    
    return imports;
  }

  /**
   * Parse C# using statements
   * Handles: using Namespace;, using static Namespace.Type;, using Alias = Namespace.Type;
   */
  private parseCSharpImports(line: string, lineNum: number): ImportStatement[] {
    const imports: ImportStatement[] = [];
    
    // using Alias = Namespace.Type;
    const aliasMatch = line.match(/^\s*using\s+(\w+)\s*=\s*([\w.]+)\s*;/);
    if (aliasMatch) {
      const alias = aliasMatch[1];
      const module = aliasMatch[2];
      imports.push({
        module,
        symbols: [alias],
        isDefault: true,
        line: lineNum,
        raw: line
      });
      return imports;
    }
    
    // using static Namespace.Type;
    const staticMatch = line.match(/^\s*using\s+static\s+([\w.]+)\s*;/);
    if (staticMatch) {
      const module = staticMatch[1];
      imports.push({
        module,
        symbols: ['*'],
        isDefault: false,
        line: lineNum,
        raw: line
      });
      return imports;
    }
    
    // using Namespace; or using Namespace.SubNamespace;
    const usingMatch = line.match(/^\s*using\s+([\w.]+)\s*;/);
    if (usingMatch) {
      const module = usingMatch[1];
      imports.push({
        module,
        symbols: [module.split('.').pop() || module],
        isDefault: true,
        line: lineNum,
        raw: line
      });
    }
    
    return imports;
  }

  /**
   * Parse Go import statements
   * Handles: import "pkg", import alias "pkg", import ( "pkg1" \n "pkg2" )
   */
  private parseGoImports(line: string, lineNum: number): ImportStatement[] {
    const imports: ImportStatement[] = [];
    
    // Single import: import "pkg" or import alias "pkg" or import . "pkg" or import _ "pkg"
    const singleImportMatch = line.match(/^\s*import\s+(?:([\w._]+)\s+)?"([^"]+)"/);
    if (singleImportMatch) {
      const alias = singleImportMatch[1] || '';
      const module = singleImportMatch[2];
      const pkgName = module.split('/').pop() || module;
      
      imports.push({
        module,
        symbols: alias === '.' ? ['*'] : alias === '_' ? [] : [alias || pkgName],
        isDefault: alias !== '.' && alias !== '_',
        line: lineNum,
        raw: line
      });
      return imports;
    }
    
    // Line inside import block: "pkg" or alias "pkg"
    // (import blocks are handled line-by-line, so each line inside gets parsed separately)
    const blockLineMatch = line.match(/^\s*(?:([\w._]+)\s+)?"([^"]+)"\s*$/);
    if (blockLineMatch) {
      const alias = blockLineMatch[1] || '';
      const module = blockLineMatch[2];
      const pkgName = module.split('/').pop() || module;
      
      imports.push({
        module,
        symbols: alias === '.' ? ['*'] : alias === '_' ? [] : [alias || pkgName],
        isDefault: alias !== '.' && alias !== '_',
        line: lineNum,
        raw: line
      });
    }
    
    return imports;
  }

  /**
   * Resolve module path to actual file path
   */
  private resolveModulePath(module: string, sourceFile: string, allFiles: string[]): string | null {
    const sourceDir = path.dirname(sourceFile);
    const extension = path.extname(sourceFile);
    
    // Verbose dependency resolution logging removed for performance
    
    // Handle Python package imports (e.g., "acme_shop.cycle_simple_b")
    let moduleVariants = [module];
    if (module.includes('.')) {
      const parts = module.split('.');
      // Add individual parts for resolution
      moduleVariants.push(parts[parts.length - 1]); // Last part (e.g., "cycle_simple_b")
      // Add path-based variants
      moduleVariants.push(parts.join('/')); // Convert dots to slashes
      moduleVariants.push(parts.join(path.sep)); // Platform-specific separator
    }
    
    const candidates: string[] = [];
    
    // Try all module variants
    for (const moduleVariant of moduleVariants) {
      candidates.push(
        // Relative imports from source directory
        path.resolve(sourceDir, moduleVariant + extension),
        path.resolve(sourceDir, moduleVariant, 'index' + extension),
        path.resolve(sourceDir, moduleVariant + '.py'),
        path.resolve(sourceDir, moduleVariant + '.ts'),
        path.resolve(sourceDir, moduleVariant + '.js'),
        
        // Look for files with matching names anywhere in workspace
        ...allFiles.filter(f => {
          const fileName = path.basename(f, path.extname(f));
          const filePath = f;
          
          // Exact filename match
          if (fileName === moduleVariant) {
            return true;
          }
          
          // Path contains the module
          if (filePath.includes(moduleVariant)) {
            return true;
          }
          
          // For package imports, check if path matches package structure
          if (module.includes('.')) {
            const packagePath = module.replace(/\./g, path.sep);
            if (filePath.includes(packagePath)) {
              return true;
            }
            
            // Check if the file path ends with the expected structure
            const expectedPath = packagePath + path.extname(f);
            if (filePath.endsWith(expectedPath)) {
              return true;
            }
            
            // Special case: when we're inside a package directory and importing from same package
            // e.g., we're in /acme_shop/ and importing "acme_shop.other_module"
            const parts = module.split('.');
            if (parts.length >= 2) {
              const lastPart = parts[parts.length - 1];
              if (fileName === lastPart && filePath.includes(parts[0])) {
                return true;
              }
            }
          }
          
          return false;
        })
      );
    }
    
    // Remove duplicates and normalize paths
    const uniqueCandidates = [...new Set(candidates.map(c => path.normalize(c)))];
    
    // Find the first candidate that exists in allFiles
    for (const candidate of uniqueCandidates) {
      // Check exact match first
      if (allFiles.includes(candidate)) {
        return candidate;
      }
      
      // Check case-insensitive match (for cross-platform compatibility)
      const match = allFiles.find(f => path.normalize(f).toLowerCase() === candidate.toLowerCase());
      if (match) {
        return match;
      }
    }
    
    // Fallback: find by filename only (for cases where path resolution fails)
    for (const moduleVariant of moduleVariants) {
      const match = allFiles.find(f => {
        const fileName = path.basename(f, path.extname(f));
        
        // Direct filename match
        if (fileName === moduleVariant) {
          return true;
        }
        
        // For Python package imports, also check if we're in the same package directory
        if (module.includes('.')) {
          const parts = module.split('.');
          const lastPart = parts[parts.length - 1];
          
          if (fileName === lastPart) {
            // Check if this file is in a directory that matches the package structure
            const sourcePackageDir = path.dirname(sourceFile);
            const candidatePackageDir = path.dirname(f);
            
            // If both files are in the same directory and that directory contains the package name
            if (sourcePackageDir === candidatePackageDir && sourcePackageDir.includes(parts[0])) {
              return true;
            }
            
            // Also check if the file path contains the expected package structure
            const packageStructure = parts.join(path.sep);
            if (f.includes(packageStructure)) {
              return true;
            }
          }
        }
        
        return false;
      });
      if (match) {
        return match;
      }
    }
    
    // No resolution found
    return null;
  }

  /**
   * Resolve function call target to file
   */
  private resolveCallTarget(callee: string, sourceFile: string, allFiles: string[]): string | null {
    // Simple heuristic: find files that might contain this function
    return allFiles.find(file => {
      const content = this.workspaceFiles.get(file);
      if (!content) return false;
      
      // Look for function definitions
      const patterns = [
        new RegExp(`def\\s+${callee}\\s*\\(`, 'i'), // Python
        new RegExp(`function\\s+${callee}\\s*\\(`, 'i'), // JavaScript
        new RegExp(`${callee}\\s*\\(.*\\)\\s*{`, 'i'), // TypeScript/Java/C#
        new RegExp(`${callee}\\s*=\\s*\\(`, 'i'), // Arrow functions
      ];
      
      return patterns.some(pattern => pattern.test(content));
    }) || null;
  }

  /**
   * Fast module path resolution using pre-built indexes.
   * O(1) average per lookup instead of O(N).
   */
  private resolveModulePathFast(module: string, sourceFile: string): string | null {
    if (!this.fileIndex) {
      return null;
    }
    
    const sourceDir = path.dirname(sourceFile);
    const extension = path.extname(sourceFile).toLowerCase();
    const { byBasename, byNormalizedPath, normalizedPathSet, byPackagePath } = this.fileIndex;

    const allowedExtensionsForSource = (sourceExt: string): Set<string> => {
      if (sourceExt === '.py') return new Set(['.py']);
      if (['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'].includes(sourceExt)) {
        return new Set(['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs']);
      }
      if (sourceExt === '.java') return new Set(['.java']);
      if (sourceExt === '.cs') return new Set(['.cs']);
      if (sourceExt === '.go') return new Set(['.go']);
      return new Set();
    };

    const allowedTargetExts = allowedExtensionsForSource(extension);
    const filterByAllowedExts = (candidates: string[]): string[] => {
      if (allowedTargetExts.size === 0) return candidates;
      return candidates.filter((c) => allowedTargetExts.has(path.extname(c).toLowerCase()));
    };

    const chooseBestCandidate = (candidates: string[]): string | null => {
      candidates = filterByAllowedExts(candidates);
      if (candidates.length === 0) return null;
      if (candidates.length === 1) return candidates[0];

      // Prefer same directory
      for (const candidate of candidates) {
        if (path.dirname(candidate) === sourceDir) {
          return candidate;
        }
      }

      // Prefer matching extension (when present)
      const sameExt = candidates.filter((c) => path.extname(c).toLowerCase() === extension);
      if (sameExt.length === 1) return sameExt[0];
      if (sameExt.length > 1) candidates = sameExt;

      // Prefer shortest relative path
      let best = candidates[0];
      let bestScore = Number.POSITIVE_INFINITY;
      for (const candidate of candidates) {
        const rel = path.relative(sourceDir, path.dirname(candidate));
        const score = rel.split(path.sep).filter(Boolean).length;
        if (score < bestScore) {
          best = candidate;
          bestScore = score;
        }
      }
      return best;
    };

    const stripKnownExt = (key: string): string => key.replace(/\.(ts|tsx|js|jsx|mjs|cjs|py|java|cs|go|rs|rb|php)$/i, '');
    
    // Build module variants
    let moduleVariants = [module];
    if (module.includes('.')) {
      const parts = module.split('.');
      moduleVariants.push(parts[parts.length - 1]); // Last part
      moduleVariants.push(parts.join('/')); // Dots to slashes
    }
    
    // Try relative path resolution first (O(1) lookup)
    for (const moduleVariant of moduleVariants) {
      const candidates: string[] = [];

      if (extension === '.py') {
        candidates.push(
          path.resolve(sourceDir, moduleVariant + '.py'),
          path.resolve(sourceDir, moduleVariant, '__init__.py')
        );
      } else if (['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'].includes(extension)) {
        candidates.push(
          path.resolve(sourceDir, moduleVariant + '.ts'),
          path.resolve(sourceDir, moduleVariant + '.tsx'),
          path.resolve(sourceDir, moduleVariant + '.js'),
          path.resolve(sourceDir, moduleVariant + '.jsx'),
          path.resolve(sourceDir, moduleVariant + '.mjs'),
          path.resolve(sourceDir, moduleVariant + '.cjs'),
          path.resolve(sourceDir, moduleVariant, 'index.ts'),
          path.resolve(sourceDir, moduleVariant, 'index.tsx'),
          path.resolve(sourceDir, moduleVariant, 'index.js'),
          path.resolve(sourceDir, moduleVariant, 'index.jsx')
        );
      } else if (extension === '.go') {
        // Go imports are package paths; try to find matching .go files
        // Go packages are directories, so look for any .go file in a matching dir
        const pkgName = moduleVariant.split('/').pop() || moduleVariant;
        candidates.push(
          path.resolve(sourceDir, moduleVariant + '.go'),
          path.resolve(sourceDir, pkgName + '.go'),
          path.resolve(sourceDir, moduleVariant, pkgName + '.go')
        );
      } else {
        candidates.push(
          path.resolve(sourceDir, moduleVariant + extension),
          path.resolve(sourceDir, moduleVariant, 'index' + extension)
        );
      }
      
      for (const candidate of candidates) {
        const normalized = path.normalize(candidate);
        const normalizedLower = normalized.toLowerCase();
        const match = byNormalizedPath.get(normalizedLower);
        if (match) return match;
        if (normalizedPathSet.has(normalizedLower)) {
          return byNormalizedPath.get(normalizedLower) || normalized;
        }
      }
    }
    
    // Try basename index (O(1) average)
    for (const moduleVariant of moduleVariants) {
      const filesWithBasename = byBasename.get(moduleVariant.toLowerCase());
      if (filesWithBasename && filesWithBasename.length > 0) {
        const chosen = chooseBestCandidate(filesWithBasename);
        if (chosen) return chosen;
      }
    }

    // Try package/path index for dotted imports and slash/path-alias imports.
    const packageKeys = new Set<string>();
    if (module.includes('.')) {
      packageKeys.add(module.replace(/\./g, '/'));
    }
    for (const variant of moduleVariants) {
      const normalizedVariant = variant.replace(/\\/g, '/');
      if (normalizedVariant.includes('/') && !normalizedVariant.startsWith('.')) {
        packageKeys.add(normalizedVariant);

        // Scoped imports: @scope/pkg/path
        if (normalizedVariant.startsWith('@')) {
          packageKeys.add(normalizedVariant.slice(1));
          const segs = normalizedVariant.split('/');
          if (segs.length >= 2) {
            packageKeys.add(segs.slice(1).join('/'));
          }
        }
      }
    }

    for (const key of packageKeys) {
      const keyNoExt = stripKnownExt(key).replace(/^\//, '');
      const keyLower = keyNoExt.toLowerCase();
      const matches = byPackagePath.get(keyLower);
      if (matches && matches.length > 0) {
        const chosen = chooseBestCandidate(matches);
        if (chosen) return chosen;
      }
    }
    
    return null;
  }

  /**
   * Fast call target resolution using cached file contents.
   * Searches only files that might match based on basename heuristics.
   */
  private resolveCallTargetFast(callee: string, sourceFile: string): string | null {
    if (!this.fileIndex) {
      return null;
    }
    
    // Extract the module part from callee (e.g., "module.function" -> "module")
    const parts = callee.split('.');
    if (parts.length < 2) {
      return null; // Not a qualified call
    }
    
    const moduleName = parts[0];
    
    // Try to find files matching the module name (O(1) lookup)
    const candidateFiles = this.fileIndex.byBasename.get(moduleName) || [];
    
    // Search only candidate files instead of all files
    const patterns = [
      new RegExp(`def\\s+${parts[parts.length - 1]}\\s*\\(`, 'i'),
      new RegExp(`function\\s+${parts[parts.length - 1]}\\s*\\(`, 'i'),
      new RegExp(`${parts[parts.length - 1]}\\s*\\(.*\\)\\s*{`, 'i'),
      new RegExp(`${parts[parts.length - 1]}\\s*=\\s*\\(`, 'i'),
    ];
    
    for (const file of candidateFiles) {
      const content = this.workspaceFiles.get(file);
      if (content && patterns.some(pattern => pattern.test(content))) {
        return file;
      }
    }
    
    return null;
  }

  /**
   * Detect if a function call is likely external
   */
  private isLikelyExternalCall(callExpr: string, fileExtension: string): boolean {
    // Skip obviously local calls
    if (callExpr.startsWith('this.') || callExpr.startsWith('self.')) {
      return false;
    }
    
    // Look for module-qualified calls
    const hasModulePrefix = /^\w+\.\w+/.test(callExpr);
    return hasModulePrefix;
  }

  /**
   * Calculate import strength based on number of symbols and usage patterns
   */
  private calculateImportStrength(imp: ImportStatement): number {
    let strength = 0.7; // Base strength
    
    // More symbols = stronger dependency
    strength += Math.min(0.2, imp.symbols.length * 0.05);
    
    // Default imports are typically stronger
    if (imp.isDefault) {
      strength += 0.1;
    }
    
    return Math.min(1.0, strength);
  }

  /**
   * Detect circular dependencies in the link graph
   */
  private detectCircularDependencies(links: DependencyLink[]): void {
    const graph: Map<string, Set<string>> = new Map();
    
    // Build adjacency list
    for (const link of links) {
      if (!graph.has(link.source)) {
        graph.set(link.source, new Set());
      }
      graph.get(link.source)!.add(link.target);
    }
    
    // Detect cycles using DFS
    const visited = new Set<string>();
    const recursionStack = new Set<string>();
    
    const hasCycle = (node: string, path: string[]): string[] | null => {
      if (recursionStack.has(node)) {
        const cycleStart = path.indexOf(node);
        return path.slice(cycleStart);
      }
      
      if (visited.has(node)) {
        return null;
      }
      
      visited.add(node);
      recursionStack.add(node);
      
      const neighbors = graph.get(node) || new Set();
      for (const neighbor of neighbors) {
        const cycle = hasCycle(neighbor, [...path, node]);
        if (cycle) {
          return cycle;
        }
      }
      
      recursionStack.delete(node);
      return null;
    };
    
    // Mark circular dependencies
    for (const [node, _] of graph) {
      if (!visited.has(node)) {
        const cycle = hasCycle(node, []);
        if (cycle) {
          // Mark all links in the cycle as circular
          for (let i = 0; i < cycle.length; i++) {
            const source = cycle[i];
            const target = cycle[(i + 1) % cycle.length];
            
            const link = links.find(l => l.source === source && l.target === target);
            if (link) {
              link.type = 'circular';
              link.strength = Math.min(1.0, link.strength + 0.3);
            }
          }
        }
      }
    }
  }

  /**
   * Merge bidirectional relationships
   */
  private mergeBidirectionalLinks(links: DependencyLink[]): void {
    for (let i = 0; i < links.length; i++) {
      const link1 = links[i];
      
      // Find reverse link
      const reverseIndex = links.findIndex((link2, j) => 
        j > i && link2.source === link1.target && link2.target === link1.source
      );
      
      if (reverseIndex !== -1) {
        const link2 = links[reverseIndex];
        
        // Merge into bidirectional link
        link1.bidirectional = true;
        link1.symbols = [...new Set([...link1.symbols, ...link2.symbols])];
        link1.lines = [...link1.lines, ...link2.lines];
        link1.strength = Math.min(1.0, link1.strength + link2.strength * 0.5);
        
        // Remove the reverse link
        links.splice(reverseIndex, 1);
      }
    }
  }

  /**
   * Load file contents into cache using fast filesystem reads.
   * Uses parallel batching for performance on large workspaces.
   */
  private async loadFileContents(files: string[], onProgress?: DependencyProgressCallback): Promise<void> {
    this.workspaceFiles.clear();
    
    // Process in parallel batches for performance
    const BATCH_SIZE = 50;
    for (let i = 0; i < files.length; i += BATCH_SIZE) {
      const batch = files.slice(i, i + BATCH_SIZE);
      const results = await Promise.allSettled(
        batch.map(async (filePath) => {
          const uri = vscode.Uri.file(filePath);
          const content = await vscode.workspace.fs.readFile(uri);
          return { filePath, content: Buffer.from(content).toString('utf-8') };
        })
      );
      
      for (const result of results) {
        if (result.status === 'fulfilled') {
          this.workspaceFiles.set(result.value.filePath, result.value.content);
        }
        // Skip failed files silently
      }
      
      // Report progress
      onProgress?.(Math.min(i + BATCH_SIZE, files.length), files.length, `Reading files (${Math.min(i + BATCH_SIZE, files.length)}/${files.length})...`);
    }
  }
}