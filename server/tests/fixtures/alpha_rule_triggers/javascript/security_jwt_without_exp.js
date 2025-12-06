// Should trigger: security.jwt_without_exp
const jwt = require('jsonwebtoken');

function createToken(userId) {
    const payload = { userId };  // missing exp claim
    return jwt.sign(payload, "secret");
}
