// Should trigger: arch.external_integration
// Fetch API - external HTTP call
async function fetchUserData(userId) {
    const response = await fetch(`https://api.example.com/users/${userId}`);
    return response.json();
}

// XMLHttpRequest - external call
function loadData(url) {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', url);
    xhr.send();
}

// Axios HTTP client
const axios = require('axios');

async function postData(data) {
    const result = await axios.post('/api/submit', data);
    return result.data;
}
