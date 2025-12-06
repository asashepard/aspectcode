// Should trigger: naming.project_term_inconsistency
// Rule detects inconsistent verb usage for same noun phrase (e.g., getUser vs fetchUser)

class UserService {
    getUser(id: number): void {}  // Uses "get" verb
    
    fetchUser(id: number): void {}  // Uses "fetch" verb - inconsistent!
    
    loadUser(id: number): void {}  // Uses "load" verb - inconsistent!
}

class OrderManager {
    createOrder(data: any): void {}
    
    makeOrder(data: any): void {}  // "make" is synonym for "create" - inconsistent!
}
