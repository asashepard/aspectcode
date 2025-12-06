/**
 * Alpha TypeScript Test Project
 * 
 * This project contains intentional TypeScript issues that should be caught
 * by alpha TypeScript rules:
 * - lang.ts_loose_equality
 * - types.ts_any_overuse
 * - types.ts_narrowing_missing  
 * - types.ts_nullable_unchecked
 */

// types.ts_any_overuse - Excessive use of any type
function processData(data: any): any {  // ERROR: any overuse
    const result: any = {};  // ERROR: any overuse
    
    // lang.ts_loose_equality - Loose equality operators
    if (data == null) {  // ERROR: should use ===
        return null;
    }
    
    if (data.value != undefined) {  // ERROR: should use !==
        result.hasValue = true;
    }
    
    // More loose equality examples
    if (data.count == 0) {  // ERROR: should use ===
        result.isEmpty = true;
    }
    
    if (data.name == "") {  // ERROR: should use ===
        result.noName = true;
    }
    
    return result;
}

// types.ts_nullable_unchecked - Nullable types not checked
interface User {
    name: string;
    email?: string;  // Optional property
    profile: UserProfile | null;  // Nullable type
}

interface UserProfile {
    bio: string;
    avatar: string;
}

function displayUser(user: User): string {
    // ERROR: accessing optional property without check
    const emailDomain = user.email.split('@')[1];  
    
    // ERROR: accessing nullable property without check
    const bio = user.profile.bio;
    
    // ERROR: chaining on nullable without check
    const avatarUrl = user.profile.avatar.toLowerCase();
    
    return `${user.name} - ${emailDomain} - ${bio}`;
}

// types.ts_narrowing_missing - Missing type narrowing
function handleValue(value: string | number | null): string {
    // ERROR: No type narrowing for union type
    return value.toString();  // Could fail if value is null
}

function processInput(input: unknown): string {
    // ERROR: No type narrowing for unknown
    return input.toUpperCase();  // Could fail if input is not a string
}

// More nullable unchecked examples
class UserService {
    private cache: Map<string, User> | null = null;
    
    getUser(id: string): User | null {
        // ERROR: accessing nullable property without check
        return this.cache.get(id) || null;
    }
    
    getUserEmail(id: string): string {
        const user = this.getUser(id);
        // ERROR: accessing nullable return without check
        return user.email || "no-email";  // user could be null
    }
}

// Complex any overuse example
class DataManager {
    // ERROR: any in class properties
    private data: any = {};
    private config: any;
    
    // ERROR: any in method signatures
    setData(key: string, value: any): void {
        this.data[key] = value;
    }
    
    getData(key: string): any {  // ERROR: any return type
        return this.data[key];
    }
    
    // ERROR: any in generic
    process<T = any>(items: T[]): any[] {
        return items.map((item: any) => this.transform(item));
    }
    
    private transform(item: any): any {  // ERROR: any parameters and return
        // More loose equality
        if (item == null) return {};  // ERROR: loose equality
        if (item.id == undefined) return item;  // ERROR: loose equality
        
        return { ...item, processed: true };
    }
}

// Problematic type coercion with loose equality
function validateInput(input: any): boolean {
    // These all use loose equality and can have unexpected behavior
    if (input == false) return false;  // ERROR: 0, "", [] all match
    if (input == 0) return false;     // ERROR: false, "", [] all match  
    if (input == "") return false;    // ERROR: 0, false, [] all match
    if (input == []) return false;    // ERROR: "", 0, false all match
    
    return true;
}

// Missing type guards
function isString(value: unknown): boolean {
    return typeof value === "string";  // Good type guard
}

function processUnknown(value: unknown): string {
    // Should use type guard but doesn't
    if (isString(value)) {
        return value;  // This is OK - type narrowed
    }
    
    // ERROR: No type narrowing here
    return value.toString();  // Could fail
}

// Array of any (overuse)
const items: any[] = [1, "two", { three: 3 }];  // ERROR: any array

// Function with complex nullable issues
function getNestedProperty(obj: Record<string, any> | null): string {
    // ERROR: Multiple nullable access without checks
    return obj.user.profile.settings.theme;  // Deep nullable chain
}

export { processData, displayUser, handleValue, DataManager };