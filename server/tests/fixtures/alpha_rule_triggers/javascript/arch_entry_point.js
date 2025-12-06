// Should trigger: arch.entry_point
// Express HTTP endpoint
const express = require('express');

const app = express();

// HTTP GET handler - entry point
app.get('/api/users', (req, res) => {
    res.json({ users: [] });
});

// HTTP POST handler - entry point
app.post('/api/users', (req, res) => {
    res.json({ created: true });
});

// Event listener - entry point
window.addEventListener('load', () => {
    console.log('Page loaded');
});

// Click handler
document.getElementById('btn').onclick = function() {
    console.log('Button clicked');
};
