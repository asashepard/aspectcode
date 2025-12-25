# Alpha Profile: KB-Enriching Rules

This document describes the streamlined alpha profile focused exclusively on **KB-enriching rules**rules that provide architectural intelligence for AI coding agents rather than reporting issues.

## Profile Philosophy

The alpha profile exists to populate the `.aspect/` knowledge base with architectural context. These rules:

- Have `display_mode: "kb-only"` or `surface: "kb"` (not shown in Problems panel)
- Use `severity: "info"` (informational, not actionable warnings)
- Map "what exists" in the codebase, not "what's wrong"
- Power the `.aspect/architecture.md`, `.aspect/map.md`, and `.aspect/context.md` files

## Active Rules (7 total)

| Rule ID | Purpose | KB Contribution |
|---------|---------|-----------------|
| `arch.entry_point` | HTTP handlers, CLI commands, main functions | -> `context.md` Entry Points |
| `arch.external_integration` | HTTP clients, databases, message queues | -> `context.md` External Integrations |
| `arch.data_model` | ORM models, dataclasses, interfaces | -> `map.md` Data Models |
| `arch.global_state_usage` | Mutable global state, singletons | -> `architecture.md` Shared State |
| `imports.cycle.advanced` | Circular import dependencies | -> `architecture.md` Circular Dependencies |
| `architecture.critical_dependency` | High-impact hub symbols | -> `architecture.md` Critical Dependencies |
| `analysis.change_impact` | Change blast radius analysis | -> `architecture.md` Change Impact |

## Rule Details

### Core KB Rules (used in context.md and map.md)

**`arch.entry_point`**
- Detects HTTP handlers, CLI commands, main functions, event listeners
- Powers the "Entry Points" section in context.md
- Helps AI agents understand where code execution starts

**`arch.external_integration`**
- Detects HTTP clients, database connections, message queues, SDKs
- Powers the "External Integrations" section in context.md
- Helps AI agents understand system boundaries

**`arch.data_model`**
- Detects ORM models, dataclasses, Pydantic models, TypeScript interfaces
- Powers the "Data Models" section in map.md
- Helps AI agents understand data structures

### Extended KB Rules (used in architecture.md)

**`arch.global_state_usage`**
- Maps mutable global state and singleton patterns
- Powers the "Shared State" section in architecture.md
- Helps AI agents understand stateful dependencies

**`imports.cycle.advanced`**
- Detects circular import dependencies using SCC analysis
- Powers the "Circular Dependencies" section in architecture.md
- Helps AI agents avoid tightly coupled changes

**`architecture.critical_dependency`**
- Identifies symbols with many dependents (high-impact hubs)
- Powers the "Critical Dependencies" section in architecture.md
- Helps AI agents understand blast radius of changes

**`analysis.change_impact`**
- Analyzes which symbols would be affected by changes
- Powers the "Change Impact" section in architecture.md
- Helps AI agents understand refactoring risk

## Removed from Alpha Profile

The following rule categories were removed because they report issues rather than provide architectural intelligence:

- **Security rules** (`sec.*`, `security.*`)
- **Bug detection** (`bug.*`)
- **Complexity** (`complexity.*`)
- **Concurrency** (`concurrency.*`)
- **Error handling** (`errors.*`)
- **Dead code** (`deadcode.*`)
- **Style** (`style.*`)
- **Testing** (`test.*`)
- **Naming** (`naming.*`, `ident.*`)

_Last updated: December 2025_
