// Should trigger: concurrency.blocking_in_async
import fs from 'fs';

async function fetchData(): Promise<string> {
    const data = fs.readFileSync('file.txt', 'utf-8');  // blocking call in async
    return data;
}
