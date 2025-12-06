// Part of imports.cycle.advanced fixture - this file imports ImportsCycleAdvanced back
// Should trigger: imports.cycle.advanced
package fixtures.java;

import fixtures.java.ImportsCycleAdvanced;

public class ImportsCycleAdvancedB {
    public String functionB() {
        ImportsCycleAdvanced a = new ImportsCycleAdvanced();
        return a.functionA() + " from B";
    }
}
