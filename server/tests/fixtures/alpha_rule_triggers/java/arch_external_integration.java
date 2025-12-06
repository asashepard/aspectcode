// Should trigger: arch.external_integration
package com.example.service;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URI;
import java.sql.*;

// HTTP client - external integration
public class ExternalService {
    
    private final HttpClient httpClient = HttpClient.newHttpClient();
    
    public String fetchUserData(String userId) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.example.com/users/" + userId))
            .GET()
            .build();
        HttpResponse<String> response = httpClient.send(request, 
            HttpResponse.BodyHandlers.ofString());
        return response.body();
    }
    
    // Database connection - external integration
    public Connection getDatabaseConnection() throws SQLException {
        return DriverManager.getConnection("jdbc:mysql://localhost/db", "user", "pass");
    }
}
