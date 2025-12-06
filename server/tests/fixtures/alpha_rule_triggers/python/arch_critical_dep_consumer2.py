# architecture.critical_dependency fixture - dependent 2
# Depends on the critical dependency

from arch_critical_dep_core import CriticalDependency, critical_utility

def consumer_two():
    """Second consumer of critical dependency."""
    dep = CriticalDependency()
    return dep.core_operation("from_two")
