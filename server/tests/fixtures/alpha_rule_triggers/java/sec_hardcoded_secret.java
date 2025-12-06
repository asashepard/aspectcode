// Should trigger: sec.hardcoded_secret
public class HardcodedSecret {
    private static final String API_KEY = "sk_live_abc123def456";
    private static final String PASSWORD = "admin123";
    private static final String SECRET = "super-secret-key";
    
    public String getCredentials() {
        return API_KEY + PASSWORD;
    }
}
