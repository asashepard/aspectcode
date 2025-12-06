// Should trigger: arch.entry_point
package com.example.api;

import org.springframework.web.bind.annotation.*;

// Spring REST controller - HTTP entry points
@RestController
@RequestMapping("/api")
public class UserController {
    
    @GetMapping("/users")
    public String getUsers() {
        return "[]";
    }
    
    @PostMapping("/users")
    public String createUser(@RequestBody String body) {
        return "{\"created\": true}";
    }
    
    // Main entry point
    public static void main(String[] args) {
        System.out.println("Starting application...");
    }
}
