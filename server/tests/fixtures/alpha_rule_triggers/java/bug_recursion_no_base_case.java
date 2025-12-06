// Should trigger: bug.recursion_no_base_case
public class InfiniteRecursion {
    public int factorial(int n) {
        // Missing base case - infinite recursion!
        return n * factorial(n - 1);
    }
}
