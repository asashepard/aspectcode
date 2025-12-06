// Should trigger: sec.sql_injection_concat
async function unsafeQuery(userInput, db) {
    const query = "SELECT * FROM users WHERE name = '" + userInput + "'";
    return await db.query(query);
}
