// Should trigger: bug.incompatible_comparison
function compareValues(): boolean {
    if (5 == "5") {  // comparing number literal with string literal
        return true;
    }
    return false;
}
