// Should trigger: sec.path_traversal
import fs from 'fs';

function readUserFile(filename: string): string {
    const path = "/app/files/" + filename;
    return fs.readFileSync(path, 'utf-8');
}
