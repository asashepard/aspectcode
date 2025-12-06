// Should trigger: bug.incompatible_comparison
function compareValues() {
    if (5 == "5") {  // comparing number literal with string literal (loose equality)
        return true;
    }
    return false;
}
