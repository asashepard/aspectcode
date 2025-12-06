// Should trigger: bug.float_equality
public class FloatEquality {
    public boolean checkEqual(double a) {
        return a == 0.1;  // Bad: direct float comparison!
    }
}
