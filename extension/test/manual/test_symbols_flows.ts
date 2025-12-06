/**
 * Manual Test Plan for symbols.md and flows.md Generation
 * 
 * Run these tests manually after loading the extension in VS Code
 */

/**
 * TEST 1: Basic Generation
 * 
 * Steps:
 * 1. Open a workspace with Python or TypeScript files
 * 2. Run: Cmd+Shift+P → "Aspect Code: Validate Full Repository"
 * 3. Wait for validation to complete
 * 4. Run: Cmd+Shift+P → "Aspect Code: Generate Instruction Files"
 * 5. Check `.aspect-code/` directory
 * 
 * Expected:
 * - .aspect-code/symbols.md exists
 * - .aspect-code/flows.md exists
 * - symbols.md contains "# Aspect Code Symbol Index"
 * - symbols.md has file sections like "## `path/to/file.py`"
 * - symbols.md has markdown tables with Symbol | Kind | Role | Calls into | Called by
 * - flows.md contains "# Aspect Code High-Impact Flows"
 * - flows.md has flow sections like "## Flow 1 – ..."
 * - flows.md has call chains with arrows (→)
 */

/**
 * TEST 2: Symbol Extraction - Python
 * 
 * Setup:
 * Create test file: test_symbols.py
 * ```python
 * class PaymentGateway:
 *     def __init__(self):
 *         pass
 *     
 *     def process_payment(self, order_id):
 *         return True
 * 
 * def handle_checkout(request):
 *     gateway = PaymentGateway()
 *     return gateway.process_payment(request.order_id)
 * 
 * def _private_helper():
 *     pass  # Should be excluded
 * ```
 * 
 * Steps:
 * 1. Run validation
 * 2. Generate instruction files
 * 3. Open .aspect-code/symbols.md
 * 4. Find the section for test_symbols.py
 * 
 * Expected:
 * - PaymentGateway class listed
 * - PaymentGateway.__init__ listed (constructor)
 * - PaymentGateway.process_payment listed (method)
 * - handle_checkout listed (function)
 * - _private_helper NOT listed (private)
 * - Roles inferred (e.g., "Processor" for process_payment)
 */

/**
 * TEST 3: Symbol Extraction - TypeScript
 * 
 * Setup:
 * Create test file: test_symbols.ts
 * ```typescript
 * export class OrderService {
 *   constructor() {}
 *   
 *   async processOrder(orderId: number): Promise<boolean> {
 *     return true;
 *   }
 * }
 * 
 * export function validateOrder(order: any): boolean {
 *   return true;
 * }
 * 
 * export const calculateTotal = (items: any[]) => {
 *   return 0;
 * };
 * 
 * export interface Order {
 *   id: number;
 * }
 * 
 * // Not exported - should be excluded
 * function privateHelper() {}
 * ```
 * 
 * Steps:
 * 1. Run validation
 * 2. Generate instruction files
 * 3. Open .aspect-code/symbols.md
 * 4. Find section for test_symbols.ts
 * 
 * Expected:
 * - OrderService class listed
 * - processOrder method listed as "async function"
 * - validateOrder function listed (role: "Validator")
 * - calculateTotal listed as "const function"
 * - Order interface listed
 * - privateHelper NOT listed (not exported)
 */

/**
 * TEST 4: Flow Construction
 * 
 * Setup:
 * Create files with findings and dependencies:
 * 
 * api.py:
 * ```python
 * from payments import process_payment
 * 
 * def handle_checkout(request):
 *     return process_payment(request.order_id)
 * ```
 * 
 * payments.py:
 * ```python
 * from db import execute_query
 * 
 * def process_payment(order_id):
 *     query = f"SELECT * FROM orders WHERE id={order_id}"  # SQL injection
 *     return execute_query(query)
 * ```
 * 
 * db.py:
 * ```python
 * def execute_query(sql):
 *     pass
 * ```
 * 
 * Steps:
 * 1. Run validation (should detect SQL injection in payments.py)
 * 2. Generate instruction files
 * 3. Open .aspect-code/flows.md
 * 4. Find flow for the SQL injection finding
 * 
 * Expected:
 * - Flow title mentions "sql injection" or similar
 * - Call chain shows: api:handle_checkout → payments:process_payment → db:execute_query
 * - Arrow points to finding location (⚠️ Finding here)
 * - Notes include security warning (🔒)
 * - Related finding references payments.py with line number
 */

/**
 * TEST 5: Empty State Handling
 * 
 * Steps:
 * 1. Open empty workspace
 * 2. Run: Aspect Code: Generate Instruction Files (without validation)
 * 3. Check .aspect-code/symbols.md and flows.md
 * 
 * Expected:
 * - Files created successfully
 * - symbols.md contains "_No files with findings or dependencies found._"
 * - flows.md contains "_No findings available. Run validation first._"
 * - No errors thrown
 */

/**
 * TEST 6: Large Workspace Limits
 * 
 * Steps:
 * 1. Open large workspace (100+ Python/TS files)
 * 2. Run validation
 * 3. Generate instruction files
 * 4. Check .aspect-code/symbols.md
 * 
 * Expected:
 * - symbols.md only contains top ~100 files (not all files)
 * - Each file section has max 20 symbols
 * - Message like "...and N more symbols in this file" if truncated
 * - Generation completes in <10 seconds
 */

/**
 * TEST 7: Instruction File Updates
 * 
 * Steps:
 * 1. Generate instruction files
 * 2. Check .github/copilot-instructions.md
 * 3. Check .cursor/rules/aspect-code.mdc
 * 4. Check CLAUDE.md
 * 
 * Expected in Copilot instructions:
 * - References to symbols.md with usage guidance
 * - References to flows.md with usage guidance
 * - 5-step workflow includes checking symbols.md and flows.md
 * 
 * Expected in Cursor rules:
 * - Symbol lookup workflow section
 * - "Called by" impact assessment section
 * - Flow preservation guidelines
 * 
 * Expected in Claude instructions:
 * - Comprehensive workflows (symbol lookup, impact analysis, etc.)
 * - Risk thresholds (10+ callers = high risk)
 * - Quick answers section mentioning symbols.md and flows.md
 */

/**
 * TEST 8: Instruction File Merge (User Content Preservation)
 * 
 * Setup:
 * 1. Create .github/copilot-instructions.md with custom content:
 * ```markdown
 * # My Custom Instructions
 * 
 * These are my project-specific rules.
 * 
 * <!-- ASPECT_CODE_START -->
 * (old Aspect Code content)
 * <!-- ASPECT_CODE_END -->
 * 
 * More custom content here.
 * ```
 * 
 * Steps:
 * 1. Generate instruction files
 * 2. Check .github/copilot-instructions.md
 * 
 * Expected:
 * - "# My Custom Instructions" preserved
 * - Content between <!-- ASPECT_CODE_START/END --> updated
 * - "More custom content here" preserved
 * - New Aspect Code content includes symbols.md and flows.md references
 */

/**
 * TEST 9: Integration with AI Prompt Generation
 * 
 * Steps:
 * 1. Run validation
 * 2. Generate instruction files
 * 3. Run: Cmd+Shift+P → "Aspect Code: Generate AI Prompt"
 * 4. Select "Generate agent prompt from my question"
 * 5. Enter: "Refactor the payment processing code"
 * 6. Check copied prompt
 * 
 * Expected:
 * - Prompt mentions reading .aspect-code files
 * - Specifically mentions symbols.md and flows.md
 * - Instructions tell agent to check symbol impact before refactoring
 * - Instructions tell agent to review flows to understand call chains
 */

/**
 * TEST 10: Performance Check
 * 
 * Steps:
 * 1. Open medium-sized workspace (50-100 files, 10-20 findings)
 * 2. Note start time
 * 3. Run: Aspect Code: Generate Instruction Files
 * 4. Note end time
 * 5. Check VS Code output channel for timing logs
 * 
 * Expected:
 * - Total time < 10 seconds
 * - Output channel shows: "Generated symbols.md (N files indexed)"
 * - Output channel shows: "Generated flows.md (N flows)"
 * - No hangs or freezes
 */

// HOW TO RUN THESE TESTS
// 
// 1. Press F5 in VS Code to launch Extension Development Host
// 2. In the dev host, open a test workspace
// 3. Follow each test's steps manually
// 4. Compare actual results with expected results
// 5. Report any failures or unexpected behavior
//
// Automated testing would require:
// - Mock AspectCodeState with sample findings
// - Mock file system with sample files
// - Mock DependencyAnalyzer with sample links
// - This is feasible but not implemented yet
