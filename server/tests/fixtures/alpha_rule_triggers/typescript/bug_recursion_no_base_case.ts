// Should trigger: bug.recursion_no_base_case
function infiniteRecursion(n: number): number {
    return infiniteRecursion(n - 1);  // no base case
}
