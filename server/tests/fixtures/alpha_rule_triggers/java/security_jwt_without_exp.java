// Should trigger: security.jwt_without_exp
import io.jsonwebtoken.Jwts;

public class JwtHandler {
    public String createToken(String subject) {
        // JWT without expiration claim!
        return Jwts.builder()
            .setSubject(subject)
            .signWith(key)
            .compact();
    }
}
