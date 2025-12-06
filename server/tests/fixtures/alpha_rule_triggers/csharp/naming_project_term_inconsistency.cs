// Should trigger: naming.project_term_inconsistency
// Rule detects inconsistent verb usage for same noun phrase (e.g., GetUser vs FetchUser)

public class UserService {
    public void GetUser(int id) {}  // Uses "Get" verb
    
    public void FetchUser(int id) {}  // Uses "Fetch" verb - inconsistent!
    
    public void LoadUser(int id) {}  // Uses "Load" verb - inconsistent!
}

class OrderManager {
    public void CreateOrder(object data) {}
    
    public void MakeOrder(object data) {}  // "Make" is synonym for "Create" - inconsistent!
}
