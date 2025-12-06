# Part of imports.cycle.advanced fixture - this file imports imports_cycle_advanced back
# Should trigger: imports.cycle.advanced

from imports_cycle_advanced import function_a

def function_b():
    """Function that depends on function_a - creates circular import."""
    return function_a() + " from B"
