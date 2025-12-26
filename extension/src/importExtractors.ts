import Parser from 'web-tree-sitter';

export type ImportEdge = { srcMod: string; dstMod: string };

// Utility to get node text
function textFor(source: string, node: Parser.SyntaxNode): string {
  return source.slice(node.startIndex, node.endIndex);
}

// Python: import statements
export function extractPythonImports(lang: Parser.Language, code: string): string[] {
  const parser = new Parser(); 
  parser.setLanguage(lang);
  const tree = parser.parse(code);
  const root = tree.rootNode;
  const out: string[] = [];
  
  const walk = (n: Parser.SyntaxNode) => {
    // grammar names: "import_statement", "import_from_statement"
    if (n.type === 'import_statement') {
      // import a, b as c
      const aliasList = n.namedChildren.find(ch => ch.type === 'import_list') || n;
      for (const ch of aliasList.namedChildren) {
        if (ch.type === 'dotted_name') {
          out.push(textFor(code, ch)); // e.g., pkg.mod
        }
      }
    } else if (n.type === 'import_from_statement') {
      // from pkg.mod import X as Y
      const moduleNode = n.namedChildren.find(ch => 
        ch.type === 'dotted_name' || ch.type === 'relative_import'
      ) || null;
      if (moduleNode) {
        const raw = textFor(code, moduleNode); // may be '.models'
        out.push(raw);
      }
    }
    
    for (const ch of n.namedChildren) {
      walk(ch);
    }
  };
  
  walk(root);
  tree.delete();
  return out;
}

// TypeScript/JavaScript: import declarations and require()
export function extractTSJSImports(lang: Parser.Language, code: string): string[] {
  const parser = new Parser(); 
  parser.setLanguage(lang);
  const tree = parser.parse(code);
  const root = tree.rootNode;
  const out: string[] = [];
  
  const walk = (n: Parser.SyntaxNode) => {
    if (n.type === 'import_statement' || n.type === 'import_declaration') {
      // import ... from "module"
      const source = n.namedChildren.find(ch => 
        ch.type === 'string' || ch.type === 'string_literal'
      );
      if (source) {
        const txt = textFor(code, source).trim();
        const m = txt.match(/^['"](.+?)['"]$/);
        if (m) out.push(m[1]);
      }
    }
    
    // CommonJS require: const X = require("mod")
    if (n.type === 'call_expression') {
      const callee = n.child(0);
      if (callee && callee.type === 'identifier' && textFor(code, callee) === 'require') {
        const arg = n.namedChildren.find(ch => 
          ch.type === 'string' || ch.type === 'string_literal'
        );
        if (arg) {
          const m = textFor(code, arg).trim().match(/^['"](.+?)['"]$/);
          if (m) out.push(m[1]);
        }
      }
    }
    
    for (const ch of n.namedChildren) {
      walk(ch);
    }
  };
  
  walk(root);
  tree.delete();
  return out;
}

// ============================================================================
// Symbol extraction for KB generation using tree-sitter AST
// ============================================================================

export interface ExtractedSymbol {
  name: string;
  kind: 'function' | 'class' | 'method' | 'interface' | 'type' | 'const' | 'property' | 'record' | 'struct' | 'enum';
  signature: string | null;
  inherits?: string; // Base class/interface
  exported: boolean;
}

/**
 * Extract symbols from Python code using tree-sitter AST
 */
export function extractPythonSymbols(lang: Parser.Language, code: string): ExtractedSymbol[] {
  const parser = new Parser();
  parser.setLanguage(lang);
  const tree = parser.parse(code);
  const root = tree.rootNode;
  const symbols: ExtractedSymbol[] = [];

  const walk = (n: Parser.SyntaxNode, inClass: boolean = false) => {
    // Function definitions
    if (n.type === 'function_definition') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      const paramsNode = n.namedChildren.find(ch => ch.type === 'parameters');
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        // Skip private functions (starting with _)
        if (!name.startsWith('_') || name === '__init__') {
          const params = paramsNode ? extractPythonParams(code, paramsNode) : [];
          const paramStr = params.join(', ');
          symbols.push({
            name: inClass ? name : name,
            kind: inClass ? 'method' : 'function',
            signature: `def ${name}(${paramStr})`,
            exported: !name.startsWith('_')
          });
        }
      }
    }
    
    // Class definitions
    if (n.type === 'class_definition') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      const argListNode = n.namedChildren.find(ch => ch.type === 'argument_list');
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        let inherits: string | undefined;
        
        if (argListNode) {
          // Get first base class
          const firstArg = argListNode.namedChildren.find(ch => 
            ch.type === 'identifier' || ch.type === 'attribute'
          );
          if (firstArg) {
            inherits = textFor(code, firstArg);
          }
        }
        
        symbols.push({
          name,
          kind: 'class',
          signature: inherits ? `class ${name}(${inherits})` : `class ${name}`,
          inherits,
          exported: !name.startsWith('_')
        });
        
        // Walk into class body for methods
        const bodyNode = n.namedChildren.find(ch => ch.type === 'block');
        if (bodyNode) {
          for (const ch of bodyNode.namedChildren) {
            walk(ch, true);
          }
          return; // Don't double-walk
        }
      }
    }

    for (const ch of n.namedChildren) {
      walk(ch, inClass);
    }
  };

  walk(root);
  tree.delete();
  return symbols;
}

function extractPythonParams(code: string, paramsNode: Parser.SyntaxNode): string[] {
  const params: string[] = [];
  for (const ch of paramsNode.namedChildren) {
    if (ch.type === 'identifier') {
      const name = textFor(code, ch);
      if (name !== 'self' && name !== 'cls') {
        params.push(name);
      }
    } else if (ch.type === 'typed_parameter' || ch.type === 'default_parameter' || ch.type === 'typed_default_parameter') {
      const idNode = ch.namedChildren.find(c => c.type === 'identifier');
      if (idNode) {
        const name = textFor(code, idNode);
        if (name !== 'self' && name !== 'cls') {
          params.push(name);
        }
      }
    }
  }
  return params.slice(0, 4); // Limit to first 4 params
}

/**
 * Extract symbols from TypeScript/JavaScript code using tree-sitter AST
 */
export function extractTSJSSymbols(lang: Parser.Language, code: string): ExtractedSymbol[] {
  const parser = new Parser();
  parser.setLanguage(lang);
  const tree = parser.parse(code);
  const root = tree.rootNode;
  const symbols: ExtractedSymbol[] = [];

  const walk = (n: Parser.SyntaxNode) => {
    // Export statements (export function, export class, etc.)
    if (n.type === 'export_statement') {
      const declaration = n.namedChildren.find(ch => 
        ch.type === 'function_declaration' || 
        ch.type === 'class_declaration' ||
        ch.type === 'interface_declaration' ||
        ch.type === 'type_alias_declaration' ||
        ch.type === 'lexical_declaration' ||
        ch.type === 'abstract_class_declaration'
      );
      
      if (declaration) {
        extractDeclaration(declaration, true);
      }
    }

    // Non-exported declarations (still might be important for architecture)
    if (['function_declaration', 'class_declaration', 'interface_declaration', 'abstract_class_declaration'].includes(n.type)) {
      // Only extract if parent is NOT export_statement
      if (n.parent?.type !== 'export_statement') {
        extractDeclaration(n, false);
      }
    }

    for (const ch of n.namedChildren) {
      walk(ch);
    }
  };

  const extractDeclaration = (n: Parser.SyntaxNode, exported: boolean) => {
    if (n.type === 'function_declaration') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      const paramsNode = n.namedChildren.find(ch => ch.type === 'formal_parameters');
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        const params = paramsNode ? extractTSJSParams(code, paramsNode) : [];
        symbols.push({
          name,
          kind: 'function',
          signature: `function ${name}(${params.join(', ')})`,
          exported
        });
      }
    }
    
    if (n.type === 'class_declaration' || n.type === 'abstract_class_declaration') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'type_identifier');
      const heritageNode = n.namedChildren.find(ch => ch.type === 'class_heritage');
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        let inherits: string | undefined;
        
        if (heritageNode) {
          const extendsClause = heritageNode.namedChildren.find(ch => ch.type === 'extends_clause');
          if (extendsClause) {
            const typeId = extendsClause.namedChildren.find(ch => ch.type === 'type_identifier' || ch.type === 'identifier');
            if (typeId) {
              inherits = textFor(code, typeId);
            }
          }
        }
        
        symbols.push({
          name,
          kind: 'class',
          signature: inherits ? `class ${name} extends ${inherits}` : `class ${name}`,
          inherits,
          exported
        });
      }
    }
    
    if (n.type === 'interface_declaration') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'type_identifier');
      const extendsClause = n.namedChildren.find(ch => ch.type === 'extends_type_clause');
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        let inherits: string | undefined;
        
        if (extendsClause) {
          const typeId = extendsClause.namedChildren.find(ch => 
            ch.type === 'type_identifier' || ch.type === 'generic_type'
          );
          if (typeId) {
            inherits = textFor(code, typeId);
          }
        }
        
        symbols.push({
          name,
          kind: 'interface',
          signature: inherits ? `interface ${name} extends ${inherits}` : `interface ${name}`,
          inherits,
          exported
        });
      }
    }
    
    if (n.type === 'type_alias_declaration') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'type_identifier');
      if (nameNode) {
        const name = textFor(code, nameNode);
        symbols.push({
          name,
          kind: 'type',
          signature: `type ${name}`,
          exported
        });
      }
    }
    
    if (n.type === 'lexical_declaration') {
      // Handle const/let declarations, including arrow functions
      for (const declarator of n.namedChildren) {
        if (declarator.type === 'variable_declarator') {
          const nameNode = declarator.namedChildren.find(ch => ch.type === 'identifier');
          if (nameNode) {
            const name = textFor(code, nameNode);
            
            // Check for arrow function assignment
            const arrowFn = declarator.namedChildren.find(ch => ch.type === 'arrow_function');
            if (arrowFn) {
              // Extract arrow function parameters
              const paramsNode = arrowFn.namedChildren.find(ch => 
                ch.type === 'formal_parameters' || ch.type === 'identifier'
              );
              let params: string[] = [];
              if (paramsNode) {
                if (paramsNode.type === 'formal_parameters') {
                  params = extractTSJSParams(code, paramsNode);
                } else if (paramsNode.type === 'identifier') {
                  params = [textFor(code, paramsNode)];
                }
              }
              const paramStr = params.length > 0 ? params.join(', ') : '';
              symbols.push({
                name,
                kind: 'const',
                signature: `const ${name} = (${paramStr}) =>`,
                exported
              });
            } else {
              // Not an arrow function - could be object, primitive, etc.
              // Try to provide at least some signature
              symbols.push({
                name,
                kind: 'const',
                signature: `const ${name}`,
                exported
              });
            }
          }
        }
      }
    }
  };

  walk(root);
  tree.delete();
  return symbols;
}

function extractTSJSParams(code: string, paramsNode: Parser.SyntaxNode): string[] {
  const params: string[] = [];
  for (const ch of paramsNode.namedChildren) {
    if (ch.type === 'identifier') {
      params.push(textFor(code, ch));
    } else if (ch.type === 'required_parameter' || ch.type === 'optional_parameter') {
      // Get the pattern (identifier or destructuring)
      const pattern = ch.namedChildren.find(c => 
        c.type === 'identifier' || c.type === 'object_pattern' || c.type === 'array_pattern'
      );
      if (pattern) {
        if (pattern.type === 'identifier') {
          params.push(textFor(code, pattern));
        } else {
          params.push('...'); // Represent destructuring
        }
      }
    } else if (ch.type === 'rest_pattern') {
      const idNode = ch.namedChildren.find(c => c.type === 'identifier');
      if (idNode) {
        params.push('...' + textFor(code, idNode));
      }
    }
  }
  return params.slice(0, 4);
}

/**
 * Extract symbols from Java code using tree-sitter AST
 */
export function extractJavaSymbols(lang: Parser.Language, code: string): ExtractedSymbol[] {
  const parser = new Parser();
  parser.setLanguage(lang);
  const tree = parser.parse(code);
  const root = tree.rootNode;
  const symbols: ExtractedSymbol[] = [];

  const walk = (n: Parser.SyntaxNode, inClass: boolean = false) => {
    // Class declarations
    if (n.type === 'class_declaration') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      const superclassNode = n.namedChildren.find(ch => ch.type === 'superclass');
      const interfacesNode = n.namedChildren.find(ch => ch.type === 'super_interfaces');
      const modifiersNode = n.namedChildren.find(ch => ch.type === 'modifiers');
      
      const isPublic = modifiersNode ? textFor(code, modifiersNode).includes('public') : false;
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        let inherits: string | undefined;
        
        if (superclassNode) {
          const typeId = superclassNode.namedChildren.find(ch => ch.type === 'type_identifier');
          if (typeId) {
            inherits = textFor(code, typeId);
          }
        }
        
        symbols.push({
          name,
          kind: 'class',
          signature: inherits ? `class ${name} extends ${inherits}` : `class ${name}`,
          inherits,
          exported: isPublic
        });
        
        // Walk into class body for methods
        const bodyNode = n.namedChildren.find(ch => ch.type === 'class_body');
        if (bodyNode) {
          for (const ch of bodyNode.namedChildren) {
            walk(ch, true);
          }
          return;
        }
      }
    }
    
    // Interface declarations
    if (n.type === 'interface_declaration') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      const extendsNode = n.namedChildren.find(ch => ch.type === 'extends_interfaces');
      const modifiersNode = n.namedChildren.find(ch => ch.type === 'modifiers');
      
      const isPublic = modifiersNode ? textFor(code, modifiersNode).includes('public') : false;
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        let inherits: string | undefined;
        
        if (extendsNode) {
          const typeId = extendsNode.namedChildren.find(ch => ch.type === 'type_identifier');
          if (typeId) {
            inherits = textFor(code, typeId);
          }
        }
        
        symbols.push({
          name,
          kind: 'interface',
          signature: inherits ? `interface ${name} extends ${inherits}` : `interface ${name}`,
          inherits,
          exported: isPublic
        });
      }
    }
    
    // Enum declarations
    if (n.type === 'enum_declaration') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      const modifiersNode = n.namedChildren.find(ch => ch.type === 'modifiers');
      
      const isPublic = modifiersNode ? textFor(code, modifiersNode).includes('public') : false;
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        symbols.push({
          name,
          kind: 'enum',
          signature: `enum ${name}`,
          exported: isPublic
        });
      }
    }
    
    // Record declarations (Java 16+)
    if (n.type === 'record_declaration') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      const modifiersNode = n.namedChildren.find(ch => ch.type === 'modifiers');
      
      const isPublic = modifiersNode ? textFor(code, modifiersNode).includes('public') : false;
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        symbols.push({
          name,
          kind: 'record',
          signature: `record ${name}`,
          exported: isPublic
        });
      }
    }
    
    // Method declarations (only when inside a class)
    if (n.type === 'method_declaration' && inClass) {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      const paramsNode = n.namedChildren.find(ch => ch.type === 'formal_parameters');
      const returnTypeNode = n.namedChildren.find(ch => 
        ch.type === 'type_identifier' || ch.type === 'void_type' || 
        ch.type === 'generic_type' || ch.type === 'array_type'
      );
      const modifiersNode = n.namedChildren.find(ch => ch.type === 'modifiers');
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        const mods = modifiersNode ? textFor(code, modifiersNode) : '';
        const isPublic = mods.includes('public') || mods.includes('protected');
        
        if (isPublic && !name.startsWith('_')) {
          const returnType = returnTypeNode ? textFor(code, returnTypeNode) : 'void';
          const params = paramsNode ? extractJavaParams(code, paramsNode) : [];
          
          symbols.push({
            name,
            kind: 'method',
            signature: `${returnType} ${name}(${params.join(', ')})`,
            exported: true
          });
        }
      }
    }

    for (const ch of n.namedChildren) {
      if (!inClass) {
        walk(ch, false);
      }
    }
  };

  walk(root);
  tree.delete();
  return symbols;
}

function extractJavaParams(code: string, paramsNode: Parser.SyntaxNode): string[] {
  const params: string[] = [];
  for (const ch of paramsNode.namedChildren) {
    if (ch.type === 'formal_parameter' || ch.type === 'spread_parameter') {
      const nameNode = ch.namedChildren.find(c => c.type === 'identifier');
      if (nameNode) {
        params.push(textFor(code, nameNode));
      }
    }
  }
  return params.slice(0, 4);
}

/**
 * Extract symbols from C# code using tree-sitter AST
 */
export function extractCSharpSymbols(lang: Parser.Language, code: string): ExtractedSymbol[] {
  const parser = new Parser();
  parser.setLanguage(lang);
  const tree = parser.parse(code);
  const root = tree.rootNode;
  const symbols: ExtractedSymbol[] = [];

  const walk = (n: Parser.SyntaxNode, inClass: boolean = false) => {
    // Class declarations
    if (n.type === 'class_declaration') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      const baseListNode = n.namedChildren.find(ch => ch.type === 'base_list');
      const modifiersNode = n.children.find(ch => ch.type === 'modifier');
      
      const modText = modifiersNode ? getAllModifiers(n, code) : '';
      const isPublic = modText.includes('public') || modText.includes('internal');
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        let inherits: string | undefined;
        
        if (baseListNode) {
          const firstBase = baseListNode.namedChildren.find(ch => 
            ch.type === 'identifier' || ch.type === 'generic_name' || ch.type === 'qualified_name'
          );
          if (firstBase) {
            inherits = textFor(code, firstBase);
          }
        }
        
        symbols.push({
          name,
          kind: 'class',
          signature: inherits ? `class ${name} : ${inherits}` : `class ${name}`,
          inherits,
          exported: isPublic
        });
        
        // Walk into class body for methods
        const bodyNode = n.namedChildren.find(ch => ch.type === 'declaration_list');
        if (bodyNode) {
          for (const ch of bodyNode.namedChildren) {
            walk(ch, true);
          }
          return;
        }
      }
    }
    
    // Interface declarations
    if (n.type === 'interface_declaration') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      const baseListNode = n.namedChildren.find(ch => ch.type === 'base_list');
      
      const modText = getAllModifiers(n, code);
      const isPublic = modText.includes('public') || modText.includes('internal');
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        let inherits: string | undefined;
        
        if (baseListNode) {
          const firstBase = baseListNode.namedChildren.find(ch => 
            ch.type === 'identifier' || ch.type === 'generic_name'
          );
          if (firstBase) {
            inherits = textFor(code, firstBase);
          }
        }
        
        symbols.push({
          name,
          kind: 'interface',
          signature: inherits ? `interface ${name} : ${inherits}` : `interface ${name}`,
          inherits,
          exported: isPublic
        });
      }
    }
    
    // Record declarations
    if (n.type === 'record_declaration') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      
      const modText = getAllModifiers(n, code);
      const isPublic = modText.includes('public') || modText.includes('internal');
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        symbols.push({
          name,
          kind: 'record',
          signature: `record ${name}`,
          exported: isPublic
        });
      }
    }
    
    // Struct declarations
    if (n.type === 'struct_declaration') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      
      const modText = getAllModifiers(n, code);
      const isPublic = modText.includes('public') || modText.includes('internal');
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        symbols.push({
          name,
          kind: 'struct',
          signature: `struct ${name}`,
          exported: isPublic
        });
      }
    }
    
    // Enum declarations
    if (n.type === 'enum_declaration') {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      
      const modText = getAllModifiers(n, code);
      const isPublic = modText.includes('public') || modText.includes('internal');
      
      if (nameNode) {
        const name = textFor(code, nameNode);
        symbols.push({
          name,
          kind: 'enum',
          signature: `enum ${name}`,
          exported: isPublic
        });
      }
    }
    
    // Method declarations (only when inside a class)
    if (n.type === 'method_declaration' && inClass) {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      const paramsNode = n.namedChildren.find(ch => ch.type === 'parameter_list');
      const returnTypeNode = n.namedChildren.find(ch => 
        ch.type === 'predefined_type' || ch.type === 'identifier' || 
        ch.type === 'generic_name' || ch.type === 'nullable_type' ||
        ch.type === 'array_type'
      );
      
      const modText = getAllModifiers(n, code);
      const isPublic = modText.includes('public') || modText.includes('protected') || modText.includes('internal');
      
      if (nameNode && isPublic) {
        const name = textFor(code, nameNode);
        const returnType = returnTypeNode ? textFor(code, returnTypeNode) : 'void';
        const params = paramsNode ? extractCSharpParams(code, paramsNode) : [];
        
        symbols.push({
          name,
          kind: 'method',
          signature: `${returnType} ${name}(${params.join(', ')})`,
          exported: true
        });
      }
    }
    
    // Property declarations (important in C#)
    if (n.type === 'property_declaration' && inClass) {
      const nameNode = n.namedChildren.find(ch => ch.type === 'identifier');
      const typeNode = n.namedChildren.find(ch => 
        ch.type === 'predefined_type' || ch.type === 'identifier' || 
        ch.type === 'generic_name' || ch.type === 'nullable_type'
      );
      
      const modText = getAllModifiers(n, code);
      const isPublic = modText.includes('public') || modText.includes('internal');
      
      if (nameNode && isPublic) {
        const name = textFor(code, nameNode);
        const type = typeNode ? textFor(code, typeNode) : 'object';
        
        symbols.push({
          name,
          kind: 'property',
          signature: `${type} ${name}`,
          exported: true
        });
      }
    }

    for (const ch of n.namedChildren) {
      if (!inClass) {
        walk(ch, false);
      }
    }
  };

  walk(root);
  tree.delete();
  return symbols;
}

function getAllModifiers(n: Parser.SyntaxNode, code: string): string {
  // Collect all modifier children
  const mods: string[] = [];
  for (const ch of n.children) {
    if (ch.type === 'modifier') {
      mods.push(textFor(code, ch));
    }
  }
  return mods.join(' ');
}

function extractCSharpParams(code: string, paramsNode: Parser.SyntaxNode): string[] {
  const params: string[] = [];
  for (const ch of paramsNode.namedChildren) {
    if (ch.type === 'parameter') {
      const nameNode = ch.namedChildren.find(c => c.type === 'identifier');
      if (nameNode) {
        params.push(textFor(code, nameNode));
      }
    }
  }
  return params.slice(0, 4);
}