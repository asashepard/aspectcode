// Should trigger: bug.recursion_no_base_case
public class InfiniteRecursion {
    public int Factorial(int n) {
        // Missing base case!
        return n * Factorial(n - 1);
    }
}
