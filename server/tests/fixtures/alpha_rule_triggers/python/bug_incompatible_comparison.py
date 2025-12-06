# Should trigger: bug.incompatible_comparison
def compare_values():
    # Number vs string literal - obvious type mismatch
    if 5 == "5":  # comparing int literal with string literal
        return True
    # Number vs boolean literal
    if 0 == False:  # comparing int with boolean
        return True
    return False

result = compare_values()
