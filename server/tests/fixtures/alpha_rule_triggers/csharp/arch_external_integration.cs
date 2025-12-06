// Should trigger: arch.external_integration
using System.Net.Http;
using System.Data.SqlClient;

namespace MyApp.Services
{
    // HTTP client - external integration
    public class ExternalService
    {
        private readonly HttpClient _httpClient = new HttpClient();

        public async Task<string> FetchUserDataAsync(string userId)
        {
            var response = await _httpClient.GetAsync($"https://api.example.com/users/{userId}");
            return await response.Content.ReadAsStringAsync();
        }

        // Database connection - external integration
        public SqlConnection GetDatabaseConnection()
        {
            return new SqlConnection("Server=localhost;Database=app;User Id=user;Password=pass;");
        }
    }
}
