"""KB-enriching rule: Detect data models and schemas.

This rule identifies data model definitions in the codebase:
- ORM models (SQLAlchemy, Django, TypeORM, Prisma, Entity Framework, JPA)
- Data classes (Python dataclass, Pydantic, attrs)
- TypeScript interfaces and types
- Schema definitions (Marshmallow, Zod, Yup, class-validator)
- Protocol Buffers and GraphQL types

PURPOSE: This is a KB-enriching rule. It does NOT flag problems - it provides
architectural intelligence that enriches the .aspect/code.md file to help
AI coding agents understand the data structures flowing through the application.

SEVERITY: "info" - These are not issues, they are structural annotations.
"""

from typing import Iterator, Dict, List, Set

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext


class ArchDataModelRule:
    """Detect data model definitions for KB enrichment."""
    
    meta = RuleMeta(
        id="arch.data_model",
        category="arch",
        tier=0,  # File-level analysis
        priority="P2",  # KB enrichment
        autofix_safety="suggest-only",
        description="Detect data model definitions (ORM models, dataclasses, interfaces, schemas)",
        langs=["python", "typescript", "javascript", "java", "csharp", "go", "ruby", "rust"],
        surface="kb"  # KB-only: powers .aspect/ architecture knowledge, not shown to users
    )
    requires = Requires(syntax=True, raw_text=True)

    def _get_node_text(self, ctx: RuleContext, node) -> str:
        """Get text content of a syntax node."""
        try:
            if hasattr(node, 'text'):
                text = node.text
                if isinstance(text, bytes):
                    return text.decode('utf-8', errors='ignore')
                return str(text)
            elif hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
                return ctx.text[node.start_byte:node.end_byte]
            elif hasattr(node, 'value'):
                return str(node.value)
            return ""
        except:
            return ""

    # ORM model base classes and decorators
    # IMPORTANT: Use specific inheritance patterns, not generic words
    ORM_PATTERNS: Dict[str, Dict[str, str]] = {
        "python": {
            # SQLAlchemy - use specific inheritance patterns
            "(DeclarativeBase)": "ORM Model (SQLAlchemy 2.0)",
            "declarative_base()": "ORM Model (SQLAlchemy)",
            "mapped_column(": "ORM Model (SQLAlchemy 2.0)",
            # Django
            "(models.Model)": "ORM Model (Django)",
            "django.db.models": "ORM Model (Django)",
            # Tortoise
            "(tortoise.Model)": "ORM Model (Tortoise)",
            # Peewee
            "(peewee.Model)": "ORM Model (Peewee)",
            # SQLModel (combines SQLAlchemy + Pydantic)
            "(SQLModel)": "ORM Model (SQLModel)",
            "(SQLModel,": "ORM Model (SQLModel)",  # Multiple inheritance
        },
        "typescript": {
            # TypeORM - only detect @Entity, not @Column (too noisy)
            "@Entity": "ORM Model (TypeORM)",
            "Entity(": "ORM Model (TypeORM)",
            # Prisma - detect PrismaClient instantiation and model access
            "new PrismaClient": "Data Model (Prisma)",
            "prisma.": "Data Model (Prisma)",  # prisma.user, prisma.post, etc.
            # Sequelize
            "Model.init": "ORM Model (Sequelize)",
            "@Table": "ORM Model (Sequelize)",
        },
        "javascript": {
            # Sequelize
            "define(": "ORM Model (Sequelize)",
            "Model.init": "ORM Model (Sequelize)",
            # Mongoose
            "mongoose.Schema": "Document Model (Mongoose)",
            "new Schema": "Document Model (Mongoose)",
        },
        "java": {
            # JPA
            "@Entity": "ORM Model (JPA)",
            "@Table": "ORM Model (JPA)",
            "@Column": "ORM Model (JPA)",
            "@Id": "ORM Model (JPA)",
            # Hibernate specific
            "Hibernate": "ORM Model (Hibernate)",
        },
        "csharp": {
            # Entity Framework
            "DbSet<": "ORM Model (Entity Framework)",
            "[Table(": "ORM Model (Entity Framework)",
            "[Key]": "ORM Model (Entity Framework)",
            "EntityTypeConfiguration": "ORM Model (Entity Framework)",
            # Dapper (uses POCOs with attributes)
        },
        "go": {
            # GORM
            "gorm.Model": "ORM Model (GORM)",
            "`gorm:": "ORM Model (GORM)",
            # SQLBoiler
            "boil.": "ORM Model (SQLBoiler)",
        },
        "ruby": {
            # ActiveRecord
            "ActiveRecord::Base": "ORM Model (ActiveRecord)",
            "ApplicationRecord": "ORM Model (ActiveRecord)",
            # Sequel
            "Sequel::Model": "ORM Model (Sequel)",
        },
        "rust": {
            # Diesel
            "#[derive(Queryable": "ORM Model (Diesel)",
            "#[diesel(": "ORM Model (Diesel)",
            # SeaORM
            "#[derive(DeriveEntityModel": "ORM Model (SeaORM)",
        },
    }

    # Data class patterns
    DATACLASS_PATTERNS: Dict[str, Dict[str, str]] = {
        "python": {
            "@dataclass": "Data Class (dataclass)",
            "dataclasses.dataclass": "Data Class (dataclass)",
            # Pydantic - use inheritance patterns
            "(BaseModel)": "Data Model (Pydantic)",
            "(BaseModel,": "Data Model (Pydantic)",
            "pydantic.BaseModel": "Data Model (Pydantic)",
            "@pydantic.dataclass": "Data Model (Pydantic dataclass)",
            # attrs
            "@attr.s": "Data Class (attrs)",
            "@attrs": "Data Class (attrs)",
            "@define": "Data Class (attrs)",
            # Named tuple
            "NamedTuple": "Data Class (NamedTuple)",
            "typing.NamedTuple": "Data Class (NamedTuple)",
            # TypedDict
            "TypedDict": "Data Class (TypedDict)",
        },
        "typescript": {
            # Basic type declarations are handled via AST in _find_ts_types()
            # Only include framework-specific patterns here
            # (TypeORM, etc. are in ORM_PATTERNS)
        },
        "javascript": {
            # Usually use TypeScript for type definitions
            # Or JSDoc @typedef
            "@typedef": "Type Definition (JSDoc)",
        },
        "java": {
            # Records (Java 14+)
            "record ": "Record",
            # Lombok
            "@Data": "Data Class (Lombok)",
            "@Value": "Value Class (Lombok)",
            "@Builder": "Builder Pattern (Lombok)",
            "@Getter": "Data Class (Lombok)",
        },
        "csharp": {
            # Records (C# 9+)
            "record ": "Record",
            "record struct": "Record Struct",
            # Data Transfer Objects (by convention)
            "Dto": "DTO",
        },
        "go": {
            # Go uses struct
            "type ": "Struct",
        },
        "ruby": {
            # Struct
            "Struct.new": "Struct",
            # Data (Ruby 3.2+)
            "Data.define": "Data Class",
            # Dry-struct
            "Dry::Struct": "Data Class (dry-struct)",
        },
        "rust": {
            "#[derive(": "Struct",
            "struct ": "Struct",
        },
    }

    # Validation/Schema patterns
    SCHEMA_PATTERNS: Dict[str, Dict[str, str]] = {
        "python": {
            # Marshmallow - detect Schema inheritance
            "(Schema)": "Schema (Marshmallow)",
            "(ma.Schema)": "Schema (Marshmallow)",
        },
        "typescript": {
            # Zod - detect schema definitions (z.object is most common entry point)
            "z.object(": "Schema (Zod)",
            # Yup - detect object schemas
            "yup.object(": "Schema (Yup)",
            # io-ts
            "t.type(": "Schema (io-ts)",
        },
        "javascript": {
            # Joi - detect object schemas
            "Joi.object(": "Schema (Joi)",
            # Yup - detect object schemas  
            "yup.object(": "Schema (Yup)",
        },
        "java": {
            # Bean Validation - skip individual annotations, too granular
        },
        "csharp": {
            # FluentValidation base class
            "AbstractValidator<": "Validation (FluentValidation)",
        },
        "go": {
            # Go validator struct tags are per-field, skip
        },
        "ruby": {
            # Dry-validation
            "Dry::Validation": "Schema (dry-validation)",
        },
        "rust": {
            # Validator crate
            "#[validate": "Validation (validator)",
        },
    }

    # GraphQL type patterns
    GRAPHQL_PATTERNS: Dict[str, Dict[str, str]] = {
        "python": {
            # Strawberry
            "@strawberry.type": "GraphQL Type (Strawberry)",
            "@strawberry.input": "GraphQL Input (Strawberry)",
            # Graphene
            "graphene.ObjectType": "GraphQL Type (Graphene)",
            "graphene.InputObjectType": "GraphQL Input (Graphene)",
            # Ariadne uses SDL
        },
        "typescript": {
            # TypeGraphQL
            "@ObjectType": "GraphQL Type (TypeGraphQL)",
            "@InputType": "GraphQL Input (TypeGraphQL)",
            "@Field": "GraphQL Field (TypeGraphQL)",
            # NestJS GraphQL
            "@Resolver": "GraphQL Resolver (NestJS)",
        },
        "javascript": {
            # Apollo Server / GraphQL.js
            "GraphQLObjectType": "GraphQL Type",
            "GraphQLInputObjectType": "GraphQL Input",
        },
        "java": {
            # GraphQL Java
            "@GraphQLApi": "GraphQL API",
            "GraphQLObjectType": "GraphQL Type",
        },
        "csharp": {
            # HotChocolate
            "[GraphQLType]": "GraphQL Type (HotChocolate)",
            "[QueryType]": "GraphQL Query (HotChocolate)",
        },
        "go": {
            # gqlgen generates types
            "gqlgen": "GraphQL (gqlgen)",
        },
        "ruby": {
            # graphql-ruby
            "GraphQL::Schema::Object": "GraphQL Type",
            "GraphQL::Schema::InputObject": "GraphQL Input",
        },
        "rust": {
            # Juniper
            "#[derive(GraphQLObject": "GraphQL Type (Juniper)",
            "#[derive(GraphQLInputObject": "GraphQL Input (Juniper)",
            # async-graphql
            "#[Object]": "GraphQL Type (async-graphql)",
        },
    }

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Detect data models and emit info-level findings."""
        if not ctx.syntax:
            return

        lang = ctx.language
        text = ctx.text
        
        # Combine all patterns for this language
        all_patterns: Dict[str, str] = {}
        for pattern_dict in [
            self.ORM_PATTERNS,
            self.DATACLASS_PATTERNS,
            self.SCHEMA_PATTERNS,
            self.GRAPHQL_PATTERNS,
        ]:
            if lang in pattern_dict:
                all_patterns.update(pattern_dict[lang])

        if not all_patterns:
            return

        # For TypeScript/JavaScript, use AST to find interfaces and types
        # PLUS pattern matching for Mongoose, Sequelize, etc.
        if lang in ("typescript", "javascript"):
            for finding in self._find_ts_types(ctx, text, lang):
                yield finding
            # Also do pattern matching for JS ORM/Schema patterns
            # (Mongoose, Sequelize, etc.)
            # Continue to pattern matching below
        
        # Track found models to avoid duplicates
        found_models: Set[str] = set()
        
        # Search for patterns in the text
        for pattern, model_type in all_patterns.items():
            if pattern in text:
                # Find all occurrences
                idx = 0
                while True:
                    idx = text.find(pattern, idx)
                    if idx == -1:
                        break
                    
                    # Get the model name if possible
                    model_name = self._extract_model_name(text, idx, pattern, lang)
                    
                    # Create a unique key for this model
                    model_key = f"{model_type}:{model_name or idx}"
                    if model_key not in found_models:
                        found_models.add(model_key)
                        
                        # Find line end for span
                        line_end = text.find('\n', idx)
                        if line_end == -1:
                            line_end = len(text)
                        
                        yield Finding(
                            rule=self.meta.id,
                            message=f"Data model: {model_type}" + (f" - {model_name}" if model_name else ""),
                            file=ctx.file_path,
                            start_byte=idx,
                            end_byte=min(idx + len(pattern) + 50, line_end),
                            severity="info",
                            meta={
                                'model_type': model_type,
                                'model_name': model_name,
                                'category': self._categorize_model(model_type),
                            }
                        )
                    
                    idx += 1

    def _find_ts_types(self, ctx: RuleContext, text: str, lang: str) -> Iterator[Finding]:
        """Find TypeScript/JavaScript type definitions using AST.
        
        Only flags types that look like actual data models, not utility types.
        Criteria for data models:
        - Has 3+ properties (indicates entity/DTO, not utility type)
        - Name contains Model, Entity, DTO, Schema, Record, Data, Response, Request
        - Located in models/, types/, entities/, schemas/ directory
        - Has decorators suggesting ORM/validation
        """
        found_types: Set[str] = set()
        
        # Check if file is in a model-like directory
        file_path_lower = ctx.file_path.lower().replace('\\', '/')
        is_model_dir = any(d in file_path_lower for d in [
            '/models/', '/entities/', '/schemas/', '/types/', '/dto/', '/dtos/',
            '/interfaces/', '/domain/', '/data/'
        ])
        
        # Model-like naming patterns
        model_name_patterns = [
            'model', 'entity', 'dto', 'schema', 'record', 'data', 
            'response', 'request', 'payload', 'input', 'output',
            'user', 'product', 'order', 'item', 'account', 'profile',
            'config', 'settings', 'options', 'params', 'args'
        ]
        
        for node in ctx.walk_nodes():
            node_type = getattr(node, 'type', '')
            
            # Interface declarations
            if node_type == 'interface_declaration':
                name = self._get_identifier_from_node(ctx, node)
                if name and name not in found_types:
                    # Check if this looks like a data model
                    if self._is_data_model_type(ctx, node, name, is_model_dir, model_name_patterns):
                        found_types.add(name)
                        start, end = ctx.node_span(node)
                        yield Finding(
                            rule=self.meta.id,
                            message=f"Data model: Interface - {name}",
                            file=ctx.file_path,
                            start_byte=start,
                            end_byte=end,
                            severity="info",
                            meta={
                                'model_type': 'Interface',
                                'model_name': name,
                                'category': 'interface',
                            }
                        )
            
            # Type alias declarations - only if they define object types
            elif node_type == 'type_alias_declaration':
                name = self._get_identifier_from_node(ctx, node)
                if name and name not in found_types:
                    # Check if this looks like a data model (object type, not utility)
                    if self._is_data_model_type(ctx, node, name, is_model_dir, model_name_patterns):
                        found_types.add(name)
                        start, end = ctx.node_span(node)
                        yield Finding(
                            rule=self.meta.id,
                            message=f"Data model: Type Alias - {name}",
                            file=ctx.file_path,
                            start_byte=start,
                            end_byte=end,
                            severity="info",
                            meta={
                                'model_type': 'Type Alias',
                                'model_name': name,
                                'category': 'type_alias',
                            }
                        )
            
            # Class declarations with Entity decorator (TypeORM)
            elif node_type == 'class_declaration':
                # Check if class has @Entity decorator
                class_text = self._get_node_text(ctx, node) or ''
                if '@Entity' in class_text or 'Entity(' in class_text:
                    name = self._get_identifier_from_node(ctx, node)
                    if name and name not in found_types:
                        found_types.add(name)
                        start, end = ctx.node_span(node)
                        yield Finding(
                            rule=self.meta.id,
                            message=f"Data model: ORM Model (TypeORM) - {name}",
                            file=ctx.file_path,
                            start_byte=start,
                            end_byte=end,
                            severity="info",
                            meta={
                                'model_type': 'ORM Model (TypeORM)',
                                'model_name': name,
                                'category': 'orm',
                            }
                        )

    def _is_data_model_type(self, ctx: RuleContext, node, name: str, is_model_dir: bool, model_name_patterns: list) -> bool:
        """Check if a type/interface looks like a data model rather than a utility type."""
        # Skip obvious utility type names
        utility_patterns = [
            'props', 'state', 'context', 'hook', 'handler', 'callback', 
            'listener', 'event', 'action', 'reducer', 'dispatch',
            'ref', 'style', 'class', 'component', 'element',
            'function', 'fn', 'func', 'util', 'helper', 'error'
        ]
        name_lower = name.lower()
        
        # Skip if name suggests utility/component type
        if any(p in name_lower for p in utility_patterns):
            return False
        
        # Skip single-letter or very short generic names
        if len(name) <= 2:
            return False
        
        # Get the node text to analyze structure
        node_text = self._get_node_text(ctx, node) or ''
        
        # Check if it has multiple properties (3+) - indicates entity/DTO
        # Count property signatures (lines with ':' that look like properties)
        property_count = node_text.count(':\n') + node_text.count(': ') + node_text.count(';\n')
        # Rough heuristic: count semicolons or property-like patterns
        import re
        property_matches = re.findall(r'\w+\s*[?]?\s*:\s*\w+', node_text)
        has_many_properties = len(property_matches) >= 3
        
        # Check if name matches data model patterns
        has_model_name = any(p in name_lower for p in model_name_patterns)
        
        # If in a model directory, be more lenient
        if is_model_dir:
            return has_many_properties or has_model_name
        
        # Otherwise, require both multiple properties AND model-like name
        # OR just a very strong model-like name (Entity, DTO, Model, Schema)
        strong_model_name = any(p in name_lower for p in ['model', 'entity', 'dto', 'schema'])
        
        return (has_many_properties and has_model_name) or strong_model_name

    def _get_identifier_from_node(self, ctx: RuleContext, node) -> str | None:
        """Extract identifier name from a node."""
        for child in getattr(node, 'children', []):
            child_type = getattr(child, 'type', '')
            if child_type in ('identifier', 'type_identifier', 'name'):
                return self._get_node_text(ctx, child)
        return None

    def _extract_model_name(self, text: str, idx: int, pattern: str, lang: str) -> str | None:
        """Extract the model name from context around the pattern."""
        import re
        
        # Get surrounding context (look backwards more for const/let declarations)
        start = max(0, idx - 150)
        end = min(len(text), idx + 200)
        context = text[start:end]
        
        # Different patterns for different languages
        if lang == "python":
            # Look for "class ClassName" before or after
            match = re.search(r'class\s+(\w+)', context)
            if match:
                return match.group(1)
        
        elif lang in ("typescript", "javascript"):
            # Look for "const schemaName = z.object" or "export const schemaName ="
            # Pattern should be before the z.object/Joi.object call
            match = re.search(r'(?:const|let|var|export\s+const)\s+(\w+)\s*=', context)
            if match:
                return match.group(1)
            # Also check for type alias
            match = re.search(r'type\s+(\w+)\s*=', context)
            if match:
                return match.group(1)
        
        elif lang in ("java", "csharp"):
            # Look for "class ClassName" or "public class ClassName"
            match = re.search(r'class\s+(\w+)', context)
            if match:
                return match.group(1)
            # Java record
            match = re.search(r'record\s+(\w+)', context)
            if match:
                return match.group(1)
        
        elif lang == "go":
            # Look for "type TypeName struct"
            match = re.search(r'type\s+(\w+)\s+struct', context)
            if match:
                return match.group(1)
        
        elif lang == "ruby":
            # Look for "class ClassName"
            match = re.search(r'class\s+(\w+)', context)
            if match:
                return match.group(1)
        
        elif lang == "rust":
            # Look for "struct StructName"
            match = re.search(r'struct\s+(\w+)', context)
            if match:
                return match.group(1)
        
        return None

    def _categorize_model(self, model_type: str) -> str:
        """Categorize model into high-level type."""
        model_lower = model_type.lower()
        
        if "orm" in model_lower or "entity" in model_lower:
            return "orm"
        elif "data class" in model_lower or "dataclass" in model_lower or "record" in model_lower:
            return "dataclass"
        elif "schema" in model_lower or "validation" in model_lower or "validator" in model_lower:
            return "schema"
        elif "graphql" in model_lower:
            return "graphql"
        elif "interface" in model_lower:
            return "interface"
        elif "type" in model_lower:
            return "type"
        elif "dto" in model_lower:
            return "dto"
        elif "pydantic" in model_lower:
            return "pydantic"
        elif "document" in model_lower:
            return "document"
        else:
            return "other"


# Module-level instance for rule registration
rule = ArchDataModelRule()

