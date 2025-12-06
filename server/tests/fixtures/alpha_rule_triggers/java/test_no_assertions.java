// Should trigger: test.no_assertions
import org.junit.Test;

public class NoAssertionTest {
    @Test
    public void testWithoutAssert() {
        int x = calculate();
        // No assertion! Test passes for any value
    }
    
    private int calculate() { return 42; }
}
