// Should trigger: sec.sql_injection_concat
async function unsafeQuery(userInput: string, db: any) {
    const query = "SELECT * FROM users WHERE name = '" + userInput + "'";
    return await db.query(query);
}
