// Should trigger: bug.float_equality
public class FloatEquality {
    public bool CheckEqual(double a) {
        return a == 0.1;  // Bad: direct float comparison!
    }
}
