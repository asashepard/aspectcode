// Should trigger: bug.incompatible_comparison
public class IncompatibleCompare {
    public bool Compare(string s) {
        return s == "test";  // Incompatible: use .Equals instead of ==
    }
}
