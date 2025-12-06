// Should trigger: imports.unused
import java.util.List;  // Not used!
import java.util.ArrayList;  // Not used!
import java.io.File;  // Not used!

public class UnusedImports {
    public void doNothing() {
        System.out.println("Hello");
    }
}
