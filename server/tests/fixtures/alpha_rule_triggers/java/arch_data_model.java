// Should trigger: arch.data_model
package com.example.model;

import javax.persistence.*;

// JPA Entity - data model
@Entity
@Table(name = "users")
public class User {
    
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    @Column(nullable = false)
    private String username;
    
    @Column(nullable = false, unique = true)
    private String email;
    
    private boolean isActive = true;
    
    // Getters and setters
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
}

// Record - data model (Java 14+)
record OrderRecord(String orderId, Long userId, double amount) {}
