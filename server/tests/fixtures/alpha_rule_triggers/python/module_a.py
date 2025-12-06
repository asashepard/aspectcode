# Should trigger: imports.cycle (when paired with module_b.py)
# This is module_a.py
from module_b import func_b

def func_a():
    return func_b()
