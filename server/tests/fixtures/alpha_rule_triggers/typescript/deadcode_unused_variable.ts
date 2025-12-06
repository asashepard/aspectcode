// Should trigger: deadcode.unused_variable
function example(): number {
    const used = 1;
    const unused = 2;  // unused variable
    return used;
}
