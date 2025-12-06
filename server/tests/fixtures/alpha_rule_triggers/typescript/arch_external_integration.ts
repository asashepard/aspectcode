// Should trigger: arch.external_integration
// HTTP client - external API call
async function fetchUserData(userId: string): Promise<any> {
    const response = await fetch(`https://api.example.com/users/${userId}`);
    return response.json();
}

// Axios HTTP client
import axios from 'axios';

async function postData(data: any): Promise<any> {
    const result = await axios.post('/api/submit', data);
    return result.data;
}

// WebSocket connection
const socket = new WebSocket('wss://api.example.com/ws');
socket.onmessage = (event) => {
    console.log(event.data);
};
