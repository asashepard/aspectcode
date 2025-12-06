# Should trigger: naming.project_term_inconsistency
# Rule detects inconsistent verb usage for same noun phrase (e.g., get_user vs fetch_user)

class UserService:
    def get_user(self, id):  # Uses "get" verb
        pass
    
    def fetch_user(self, id):  # Uses "fetch" verb - inconsistent with get_user!
        pass
    
    def load_user(self, id):  # Uses "load" verb - inconsistent with get_user!
        pass

class OrderManager:
    def create_order(self, data):
        pass
    
    def make_order(self, data):  # "make" is synonym for "create" - inconsistent!
        pass
