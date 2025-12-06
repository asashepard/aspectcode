# architecture.critical_dependency fixture - dependent 1
# Depends on the critical dependency

from arch_critical_dep_core import CriticalDependency, critical_utility

def consumer_one():
    """First consumer of critical dependency."""
    dep = critical_utility()
    return dep.core_operation("from_one")
