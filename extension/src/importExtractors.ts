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