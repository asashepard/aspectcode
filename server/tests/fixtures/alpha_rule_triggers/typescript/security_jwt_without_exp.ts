// Should trigger: security.jwt_without_exp
import jwt from 'jsonwebtoken';

function createToken(userId: string): string {
    const payload = { userId };  // missing exp claim
    return jwt.sign(payload, "secret");
}
