// Should trigger: sec.path_traversal
const fs = require('fs');

function readUserFile(filename) {
    const path = "/app/files/" + filename;
    return fs.readFileSync(path, 'utf-8');
}
