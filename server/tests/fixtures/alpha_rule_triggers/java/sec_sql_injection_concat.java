// Should trigger: sec.sql_injection_concat
import java.sql.*;

public class SqlInjection {
    public void queryUser(Connection conn, String userId) throws SQLException {
        String query = "SELECT * FROM users WHERE id = " + userId;  // SQL injection!
        Statement stmt = conn.createStatement();
        stmt.executeQuery(query);
    }
}
