// Should trigger: bug.boolean_bitwise_misuse
function checkConditions(a, b, c, d) {
    if ((a === 1) & (b > 0)) {  // using bitwise & instead of logical &&
        return true;
    }
    if ((c < 10) | (d === 5)) {  // using bitwise | instead of logical ||
        return true;
    }
    return false;
}
