from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from models import OrderStatus, UserRole

# Store Schemas
class StoreBase(BaseModel):
    name: str

class StoreCreate(StoreBase):
    pass

class Store(StoreBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Category Schemas
class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class Category(CategoryBase):
    id: int
    store_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Product Schemas (Zimeongezwa barcode na size)
class ProductBase(BaseModel):
    name: str
    barcode: Optional[str] = None
    size: Optional[str] = None
    cost_price: float = 0.0
    price: float
    quantity: int = 0
    min_stock_level: int = 5
    category_id: Optional[int] = None

class ProductCreate(ProductBase):
    pass

class Product(ProductBase):
    id: int
    store_id: int
    created_at: datetime
    category: Optional[Category] = None

    class Config:
        from_attributes = True

# Customer Schemas
class CustomerBase(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None

class CustomerCreate(CustomerBase):
    pass

class Customer(CustomerBase):
    id: int
    store_id: int
    current_balance: float
    created_at: datetime

    class Config:
        from_attributes = True

# Order Item Schemas
class OrderItemBase(BaseModel):
    product_id: int
    quantity: int

class OrderItemCreate(OrderItemBase):
    pass

class OrderItem(OrderItemBase):
    id: int
    price: float
    subtotal: float
    product: Optional[Product] = None

    class Config:
        from_attributes = True

# Order Schemas
class OrderCreate(BaseModel):
    customer_id: Optional[int] = None
    items: List[OrderItemCreate]

class Order(BaseModel):
    id: int
    store_id: int
    customer_id: Optional[int] = None
    user_id: Optional[int] = None
    total_amount: float
    status: OrderStatus
    created_at: datetime
    order_items: List[OrderItem] = []

    class Config:
        from_attributes = True

# User Schemas
class UserBase(BaseModel):
    full_name: str
    username: str
    role: UserRole = UserRole.CASHIER

class UserCreate(UserBase):
    password: str
    store_id: int

class UserLogin(BaseModel):
    username: str
    password: str

class User(UserBase):
    id: int
    store_id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
