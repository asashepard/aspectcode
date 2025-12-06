// Should trigger: concurrency.blocking_in_async
const fs = require('fs');

async function fetchData() {
    const data = fs.readFileSync('file.txt', 'utf-8');  // blocking call in async
    return data;
}
