# Dependent file for analysis.change_impact fixture
# Depends on critical_function from analysis_change_impact

from analysis_change_impact import critical_function, CriticalService

def use_critical():
    """Uses the critical function."""
    return critical_function("data1")

def use_service():
    """Uses the critical service."""
    svc = CriticalService()
    return svc.process("data2")
