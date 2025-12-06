// Should trigger: sec.sql_injection_concat
using System.Data.SqlClient;

public class SqlInjection {
    public void QueryUser(string userId) {
        string query = "SELECT * FROM users WHERE id = " + userId;
        using var cmd = new SqlCommand(query);
    }
}
