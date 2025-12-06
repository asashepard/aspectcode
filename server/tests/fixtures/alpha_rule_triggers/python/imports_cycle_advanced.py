# Part of imports.cycle.advanced fixture - this file imports imports_cycle_advanced_b
# Should trigger: imports.cycle.advanced

from imports_cycle_advanced_b import function_b

def function_a():
    """Function that depends on function_b."""
    return function_b() + " from A"
