// Should trigger: arch.data_model
// Mongoose Schema - JavaScript data model
const mongoose = require('mongoose');

const userSchema = new mongoose.Schema({
    id: { type: Number, required: true },
    username: { type: String, required: true },
    email: { type: String, required: true },
    isActive: { type: Boolean, default: true },
    createdAt: { type: Date, default: Date.now }
});

const User = mongoose.model('User', userSchema);

// Sequelize model
const { DataTypes, Model } = require('sequelize');

const Order = sequelize.define('Order', {
    orderId: DataTypes.STRING,
    userId: DataTypes.INTEGER,
    totalAmount: DataTypes.DECIMAL
});
