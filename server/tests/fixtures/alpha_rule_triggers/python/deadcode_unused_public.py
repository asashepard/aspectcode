# deadcode.unused_public fixture
# This file defines public symbols that are never used externally
# Should trigger: deadcode.unused_public

class UnusedPublicClass:
    """A public class that is never imported or used."""
    
    def unused_method(self):
        """An unused public method."""
        return "never called"

def unused_public_function():
    """A public function that is never imported anywhere."""
    return "dead code"

PUBLIC_UNUSED_CONSTANT = "never referenced"

# This is internal and is fine
def _private_helper():
    """Private helper - OK to be unused."""
    return "internal"
