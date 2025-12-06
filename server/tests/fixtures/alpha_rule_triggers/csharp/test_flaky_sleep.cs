// Should trigger: test.flaky_sleep
using NUnit.Framework;
using System.Threading;

[TestFixture]
public class FlakyTest {
    [Test]
    public void TestWithSleep() {
        Thread.Sleep(1000);  // Flaky!
        Assert.Pass();
    }
}
