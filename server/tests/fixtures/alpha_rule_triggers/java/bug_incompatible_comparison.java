// Should trigger: bug.incompatible_comparison
public class IncompatibleCompare {
    public boolean compare(String s) {
        return s == "test";  // Incompatible: use .equals instead of ==
    }
}
