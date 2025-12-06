// Should trigger: test.no_assertions
using NUnit.Framework;

[TestFixture]
public class NoAssertionTest {
    [Test]
    public void TestWithoutAssert() {
        int x = Calculate();
        // No assertion!
    }
    
    private int Calculate() => 42;
}
