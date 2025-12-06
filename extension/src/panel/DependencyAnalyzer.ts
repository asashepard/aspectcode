/**
 * Production-ready dependency analyzer for code relationships
 * Performs actual static analysis of imports, requires, and function calls
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

export class DependencyAnalyzer {
  private workspaceFiles: Map<string, string> = new Map(); // file path -> content cache
  
  /**
   * Analyze all real dependencies between workspace files
   */
  async analyzeDependencies(files: string[]): Promise<DependencyLink[]> {
    const links: DependencyLink[] = [];
    
    // Load and cache file contents
    await this.loadFileContents(files);
    
    for (const file of files) {
      const fileDependencies = await this.analyzeFileImports(file);
      const fileCalls = await this.analyzeFileCalls(file);
      
      // Convert imports to dependency links
      for (const imp of fileDependencies) {
        const resolvedTarget = this.resolveModulePath(imp.module, file, files);
        
        if (resolvedTarget) {
          links.push({
            source: file,
            target: resolvedTarget,
            type: 'import',
            strength: this.calculateImportStrength(imp),
            symbols: imp.symbols,
            lines: [imp.line],
            bidirectional: false
          });
        }
      }
      
      // Convert function calls to dependency links
      for (const call of fileCalls) {
        if (call.isExternal) {
          const resolvedTarget = this.resolveCallTarget(call.callee, file, files);
          if (resolvedTarget) {
            const existing = links.find(l => 
              l.source === file && l.target === resolvedTarget && l.type === 'call'
            );
            
            if (existing) {
              existing.symbols.push(call.callee);
              existing.lines.push(call.line);
              existing.strength = Math.min(1.0, existing.strength + 0.1);
            } else {
              links.push({
                source: file,
                target: resolvedTarget,
                type: 'call',
                strength: 0.6,
                symbols: [call.callee],
                lines: [call.line],
                bidirectional: false
              });
            }
          }
        }
      }
    }
    
    // Detect circular dependencies
    this.detectCircularDependencies(links);
    
    // Merge bidirectional relationships
    this.mergeBidirectionalLinks(links);
    
    return links;
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
    
    // from module import symbols
    const fromImportMatch = line.match(/from\s+([\w.]+)\s+import\s+(.+)/);
    if (fromImportMatch) {
      let module = fromImportMatch[1];
      const symbolsStr = fromImportMatch[2];
      const symbols = symbolsStr.split(',').map(s => s.trim().split(' as ')[0]);
      
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
    }
    
    // import module
    const importMatch = line.match(/import\s+([\w.]+)(?:\s+as\s+\w+)?/);
    if (importMatch) {
      let module = importMatch[1];
      
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
    
    return imports;
  }

  /**
   * Parse JavaScript/TypeScript import statements
   */
  private parseJavaScriptImports(line: string, lineNum: number): ImportStatement[] {
    const imports: ImportStatement[] = [];
    
    // import { symbols } from 'module'
    const namedImportMatch = line.match(/import\s*\{\s*([^}]+)\s*\}\s*from\s*['"]([^'"]+)['"]/);
    if (namedImportMatch) {
      const symbolsStr = namedImportMatch[1];
      const module = namedImportMatch[2];
      const symbols = symbolsStr.split(',').map(s => s.trim().split(' as ')[0]);
      
      imports.push({
        module,
        symbols,
        isDefault: false,
        line: lineNum,
        raw: line
      });
    }
    
    // import defaultSymbol from 'module'
    const defaultImportMatch = line.match(/import\s+(\w+)\s+from\s*['"]([^'"]+)['"]/);
    if (defaultImportMatch) {
      const symbol = defaultImportMatch[1];
      const module = defaultImportMatch[2];
      
      imports.push({
        module,
        symbols: [symbol],
        isDefault: true,
        line: lineNum,
        raw: line
      });
    }
    
    // require() calls
    const requireMatch = line.match(/(?:const|let|var)\s+(?:\{\s*([^}]+)\s*\}|(\w+))\s*=\s*require\s*\(\s*['"]([^'"]+)['"]\s*\)/);
    if (requireMatch) {
      const symbols = requireMatch[1] ? requireMatch[1].split(',').map(s => s.trim()) : [requireMatch[2]];
      const module = requireMatch[3];
      
      imports.push({
        module,
        symbols,
        isDefault: !requireMatch[1],
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
   */
  private parseCSharpImports(line: string, lineNum: number): ImportStatement[] {
    const imports: ImportStatement[] = [];
    
    const usingMatch = line.match(/using\s+([\w.]+);/);
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
   * Load file contents into cache
   */
  private async loadFileContents(files: string[]): Promise<void> {
    this.workspaceFiles.clear();
    
    for (const filePath of files) {
      try {
        const uri = vscode.Uri.file(filePath);
        const document = await vscode.workspace.openTextDocument(uri);
        this.workspaceFiles.set(filePath, document.getText());
      } catch (error) {
        console.warn(`Failed to load file ${filePath}:`, error);
      }
    }
  }
}