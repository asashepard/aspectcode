// Should trigger: sec.insecure_random
function generateToken() {
    return Math.floor(Math.random() * 1000000).toString();
}
