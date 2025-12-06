#!/usr/bin/env node
// Fetch Tree-sitter parser WASMs for Python and TypeScript/JavaScript
const fs = require('fs');
const path = require('path');
const https = require('https');

const PARSERS_DIR = path.join(__dirname, '..', 'parsers');

// Official WASM URLs from tree-sitter-wasms npm package or direct builds
const WASM_URLS = {
  'python.wasm': 'https://github.com/tree-sitter/tree-sitter-python/releases/download/v0.23.2/tree-sitter-python.wasm',
  'typescript.wasm': 'https://github.com/tree-sitter/tree-sitter-typescript/releases/download/v0.23.0/tree-sitter-typescript.wasm',
  'tsx.wasm': 'https://github.com/tree-sitter/tree-sitter-typescript/releases/download/v0.23.0/tree-sitter-tsx.wasm',
  'javascript.wasm': 'https://github.com/tree-sitter/tree-sitter-javascript/releases/download/v0.23.0/tree-sitter-javascript.wasm'
};

async function downloadWasm(name, url, dest) {
  return new Promise((resolve, reject) => {
    console.log(`Downloading ${name} from ${url}...`);
    
    const file = fs.createWriteStream(dest);
    
    https.get(url, (response) => {
      if (response.statusCode === 302 || response.statusCode === 301) {
        // Follow redirect
        https.get(response.headers.location, (redirectResponse) => {
          if (redirectResponse.statusCode === 200) {
            redirectResponse.pipe(file);
            file.on('finish', () => {
              file.close();
              console.log(`✓ Downloaded ${name} (${fs.statSync(dest).size} bytes)`);
              resolve();
            });
          } else {
            reject(new Error(`HTTP ${redirectResponse.statusCode}`));
          }
        }).on('error', reject);
      } else if (response.statusCode === 200) {
        response.pipe(file);
        file.on('finish', () => {
          file.close();
          console.log(`✓ Downloaded ${name} (${fs.statSync(dest).size} bytes)`);
          resolve();
        });
      } else {
        reject(new Error(`HTTP ${response.statusCode}`));
      }
    }).on('error', reject);
    
    file.on('error', (err) => {
      fs.unlink(dest, () => {}); // Delete partial file
      reject(err);
    });
  });
}

async function createStubFile(name, dest) {
  const stubContent = `# Stub WASM file for ${name.replace('.wasm', '')} parser
# This is a placeholder - replace with actual tree-sitter-${name.replace('.wasm', '')}.wasm
# The extension will gracefully fall back to regex if this fails to load`;
  fs.writeFileSync(dest, stubContent);
  console.log(`Created stub ${name} (download failed, will use regex fallback)`);
}

async function main() {
  try {
    if (!fs.existsSync(PARSERS_DIR)) {
      fs.mkdirSync(PARSERS_DIR, { recursive: true });
    }

    console.log('Setting up Tree-sitter parsers...');
    
    for (const [filename, url] of Object.entries(WASM_URLS)) {
      const destPath = path.join(PARSERS_DIR, filename);
      
      try {
        await downloadWasm(filename, url, destPath);
      } catch (error) {
        console.log(`Failed to download ${filename}: ${error.message}`);
        await createStubFile(filename, destPath);
      }
    }
    
    console.log('Parser setup complete');
  } catch (error) {
    console.log('Parser fetch failed (will fall back to regex):', error.message);
  }
}

if (require.main === module) {
  main();
}