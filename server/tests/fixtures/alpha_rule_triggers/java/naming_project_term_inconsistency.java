// Should trigger: naming.project_term_inconsistency
// Rule detects inconsistent verb usage for same noun phrase (e.g., getUser vs fetchUser)

public class UserService {
    public void getUser(int id) {}  // Uses "get" verb
    
    public void fetchUser(int id) {}  // Uses "fetch" verb - inconsistent!
    
    public void loadUser(int id) {}  // Uses "load" verb - inconsistent!
}

class OrderManager {
    public void createOrder(Object data) {}
    
    public void makeOrder(Object data) {}  // "make" is synonym for "create" - inconsistent!
}
