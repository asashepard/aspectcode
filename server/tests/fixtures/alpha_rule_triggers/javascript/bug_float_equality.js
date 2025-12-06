// Should trigger: bug.float_equality
function checkValue(x) {
    if (x == 0.1 + 0.2) {  // dangerous float equality
        return true;
    }
    return false;
}
