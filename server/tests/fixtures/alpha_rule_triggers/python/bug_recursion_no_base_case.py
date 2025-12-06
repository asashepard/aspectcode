# Should trigger: bug.recursion_no_base_case
def infinite_recursion(n):
    return infinite_recursion(n - 1)  # no base case
