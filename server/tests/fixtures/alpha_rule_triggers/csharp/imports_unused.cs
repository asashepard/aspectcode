// Should trigger: imports.unused
using System.Collections.Generic;  // Not used!
using System.IO;  // Not used!
using System.Text;  // Not used!

public class UnusedUsings {
    public void DoNothing() {
        Console.WriteLine("Hello");
    }
}
