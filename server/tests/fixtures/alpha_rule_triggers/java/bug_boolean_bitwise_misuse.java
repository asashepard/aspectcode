// Should trigger: bug.boolean_bitwise_misuse
public class BitwiseMisuse {
    public boolean check(int a, int b, int c, int d) {
        if ((a == 1) & (b > 0)) {  // Should be &&
            return true;
        }
        if ((c < 10) | (d == 5)) {  // Should be ||
            return true;
        }
        return false;
    }
}
