// Part of imports.cycle.advanced fixture - this file uses ImportsCycleAdvanced back
// Should trigger: imports.cycle.advanced
using System;

namespace Fixtures.CSharp
{
    public class ImportsCycleAdvancedB
    {
        public string FunctionB()
        {
            var a = new ImportsCycleAdvanced();
            return a.FunctionA() + " from B";
        }
    }
}
