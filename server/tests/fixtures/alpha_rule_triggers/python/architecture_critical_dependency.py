# architecture.critical_dependency fixture
# This file is a critical dependency bottleneck - many modules depend on it
# Should trigger: architecture.critical_dependency

class CriticalDependency:
    """A class that represents a critical architectural dependency."""
    
    def core_operation(self, data):
        """Core operation that many modules use."""
        return self._process(data)
    
    def _process(self, data):
        return {"result": data}

def critical_utility():
    """Utility function that is widely used."""
    return CriticalDependency()
