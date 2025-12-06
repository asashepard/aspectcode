// Should trigger: style.mixed_indentation
function mixedIndent() {
    if (true) {
        console.log("spaces");
	console.log("tabs");  // tab character here
    }
}
