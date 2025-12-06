# architecture.dependency_cycle_impact fixture
# This file completes the impactful dependency cycle
# Should trigger: architecture.dependency_cycle_impact

from arch_dep_cycle_a import cycle_function_a

class CycleClassB:
    """Part of a cycle that affects architecture."""
    
    def call_a(self):
        return cycle_function_a()
    
def cycle_function_b():
    """Function in the cycle - creates circular dependency."""
    return CycleClassB()
