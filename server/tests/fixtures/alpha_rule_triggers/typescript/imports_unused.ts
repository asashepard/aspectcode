// Should trigger: imports.unused
import fs from 'fs';
import path from 'path';  // unused

console.log(fs.existsSync('.'));
