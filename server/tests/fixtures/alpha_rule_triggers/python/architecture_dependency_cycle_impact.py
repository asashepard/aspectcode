# architecture.dependency_cycle_impact fixture
# This file is part of an impactful dependency cycle
# Should trigger: architecture.dependency_cycle_impact

from arch_dep_cycle_b import cycle_function_b

class CycleClassA:
    """Part of a cycle that affects architecture."""
    
    def call_b(self):
        return cycle_function_b()
    
def cycle_function_a():
    """Function in the cycle."""
    return CycleClassA()
