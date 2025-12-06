# analysis.change_impact fixture
# This file defines a critical class used by many other files
# Should trigger: analysis.change_impact

class CriticalService:
    """A critical service that many other modules depend on."""
    
    def process(self, data):
        """Critical method - changing this impacts many dependents."""
        return self._internal_process(data)
    
    def _internal_process(self, data):
        return {"processed": data}

def critical_function(param):
    """A function that is imported by many modules."""
    service = CriticalService()
    return service.process(param)
