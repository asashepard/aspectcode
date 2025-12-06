// Should trigger: arch.data_model
// TypeScript interface data model
interface User {
    id: number;
    username: string;
    email: string;
    createdAt: Date;
    isActive: boolean;
    profilePicture?: string;
}

// TypeScript type with decorator pattern
interface Order {
    orderId: string;
    userId: number;
    items: string[];
    totalAmount: number;
}

// Class-based data model
class Product {
    constructor(
        public id: number,
        public name: string,
        public price: number,
        public category: string
    ) {}
}
