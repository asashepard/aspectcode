// Part of imports.cycle.advanced fixture - this file uses ImportsCycleAdvancedB
// Should trigger: imports.cycle.advanced
using System;

namespace Fixtures.CSharp
{
    public class ImportsCycleAdvanced
    {
        public string FunctionA()
        {
            var b = new ImportsCycleAdvancedB();
            return b.FunctionB() + " from A";
        }
    }
}
