// Should trigger: security.jwt_without_exp
using System.IdentityModel.Tokens.Jwt;

public class JwtHandler {
    public string CreateToken(string subject) {
        var token = new JwtSecurityToken(
            issuer: "test",
            audience: "test"
            // No expiration!
        );
        return new JwtSecurityTokenHandler().WriteToken(token);
    }
}
