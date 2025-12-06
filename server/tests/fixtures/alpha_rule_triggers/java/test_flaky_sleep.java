// Should trigger: test.flaky_sleep
import org.junit.Test;

public class FlakyTest {
    @Test
    public void testWithSleep() throws Exception {
        Thread.sleep(1000);  // Flaky!
        assertEquals(1, 1);
    }
}
