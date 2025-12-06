// Should trigger: naming.project_term_inconsistency
// Rule detects inconsistent verb usage for same noun phrase (e.g., getUser vs fetchUser)

class UserService {
    getUser(id) {}  // Uses "get" verb
    
    fetchUser(id) {}  // Uses "fetch" verb - inconsistent!
    
    loadUser(id) {}  // Uses "load" verb - inconsistent!
}

class OrderManager {
    createOrder(data) {}
    
    makeOrder(data) {}  // "make" is synonym for "create" - inconsistent!
}
