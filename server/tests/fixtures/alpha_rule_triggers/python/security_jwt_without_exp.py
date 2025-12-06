# Should trigger: security.jwt_without_exp
import jwt

def create_token(user_id):
    payload = {"user_id": user_id}  # missing exp claim
    return jwt.encode(payload, "secret", algorithm="HS256")
