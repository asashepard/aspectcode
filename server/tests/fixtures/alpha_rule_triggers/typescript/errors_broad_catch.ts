// Should trigger: errors.broad_catch
function handleError() {
    try {
        processData();
    } catch (e) {  // too broad - catches everything
        console.log("Error:", e);
    }
}

function processData() {}
