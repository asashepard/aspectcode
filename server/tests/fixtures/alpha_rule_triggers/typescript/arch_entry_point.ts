// Should trigger: arch.entry_point
// Express HTTP endpoint
import express from 'express';

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
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded');
});
