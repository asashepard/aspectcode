// Part of imports.cycle.advanced fixture - this file imports ImportsCycleAdvancedB
// Should trigger: imports.cycle.advanced
package fixtures.java;

import fixtures.java.ImportsCycleAdvancedB;

public class ImportsCycleAdvanced {
    public String functionA() {
        ImportsCycleAdvancedB b = new ImportsCycleAdvancedB();
        return b.functionB() + " from A";
    }
}
