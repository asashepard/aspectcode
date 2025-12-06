// Should trigger: bug.recursion_no_base_case
function infiniteRecursion(n) {
    return infiniteRecursion(n - 1);  // no base case
}
