import uvicorn
from fastapi import FastAPI, HTTPException, status, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import List, Optional, Dict
from decimal import Decimal
import re

# --- Problem 1 Models (Reused) ---

class FoodCategory(str, Enum):
    """
    Enum for different food categories in the menu.
    """
    APPETIZER = "appetizer"
    MAIN_COURSE = "main_course"
    DESSERT = "dessert"
    BEVERAGE = "beverage"
    SALAD = "salad"

class FoodItemCreate(BaseModel):
    """
    Pydantic model for creating or updating a food item.
    Does not include 'id' as it is auto-generated.
    """
    name: str = Field(..., min_length=3, max_length=100, description="Name of the food item (3-100 characters)")
    description: str = Field(..., min_length=10, max_length=500, description="Description of the food item (10-500 characters)")
    category: FoodCategory = Field(..., description="Category of the food item")
    price: Decimal = Field(..., gt=0, decimal_places=2, description="Price of the food item (must be positive, max 2 decimal places)")
    is_available: bool = Field(True, description="Availability status of the food item (default True)")
    preparation_time: int = Field(..., ge=1, le=120, description="Preparation time in minutes (1-120 minutes)")
    ingredients: List[str] = Field(..., min_items=1, description="List of ingredients (at least 1 ingredient)")
    calories: Optional[int] = Field(None, gt=0, description="Calorie count (optional, must be positive if provided)")
    is_vegetarian: bool = Field(False, description="Is it vegetarian? (default False)")
    is_spicy: bool = Field(False, description="Is it spicy? (default False)")

    @field_validator('name')
    def validate_name_characters(cls, v):
        if not re.fullmatch(r'^[a-zA-Z\s]+$', v):
            raise ValueError('Name should only contain letters and spaces')
        return v.strip()

    @field_validator('price')
    def validate_price_range(cls, v):
        if not (Decimal('1.00') <= v <= Decimal('100.00')):
            raise ValueError('Price must be between $1.00 and $100.00')
        return v

    @property
    def price_category(self) -> str:
        if self.price < Decimal('10.00'):
            return "Budget"
        elif Decimal('10.00') <= self.price <= Decimal('25.00'):
            return "Mid-range"
        else:
            return "Premium"

    @property
    def dietary_info(self) -> List[str]:
        info = []
        if self.is_vegetarian:
            info.append("Vegetarian")
        if self.is_spicy:
            info.append("Spicy")
        return info

class FoodItem(FoodItemCreate):
    """
    Pydantic model for a food item including its auto-generated ID.
    Used for retrieving and storing items in the database.
    """
    id: int


# --- Problem 2 Models ---

class OrderStatus(str, Enum):
    """
    Enum for different order statuses.
    """
    PENDING = "pending"
    CONFIRMED = "confirmed"
    READY = "ready"
    DELIVERED = "delivered"

class OrderItem(BaseModel):
    """
    Simple nested model for items within an order.
    References menu item by ID and stores redundant name/price for snapshotting.
    """
    menu_item_id: int = Field(..., gt=0, description="Reference to the FoodItem ID")
    menu_item_name: str = Field(..., min_length=1, max_length=100, description="Store name for easy access")
    quantity: int = Field(..., gt=0, le=10, description="Quantity of the item (max 10)")
    unit_price: Decimal = Field(..., gt=0, decimal_places=2, description="Unit price of the item (for snapshotting)")

    @property
    def item_total(self) -> Decimal:
        """Computed property: total price for this order item."""
        return self.quantity * self.unit_price

class Customer(BaseModel):
    """
    Simple nested customer model.
    """
    name: str = Field(..., min_length=2, max_length=50, description="Customer's name")
    phone: str = Field(..., pattern=r"^\d{10}$", description="Customer's phone number (10 digits)")
    address: str = Field(..., min_length=5, description="Customer's address")

class OrderCreate(BaseModel):
    """
    Pydantic model for creating a new order.
    """
    customer: Customer
    items: List[OrderItem] = Field(..., min_items=1, description="List of items in the order (at least one item)")

class Order(OrderCreate):
    """
    Pydantic model for an existing order with its ID and status.
    """
    id: int
    status: OrderStatus = Field(OrderStatus.PENDING, description="Current status of the order")

    @property
    def total_amount(self) -> Decimal:
        """Computed property: total amount of all items in the order."""
        return sum(item.item_total for item in self.items)

    @property
    def total_amount_with_delivery(self) -> Decimal:
        """Computed property: total amount including a fixed delivery fee."""
        DELIVERY_FEE = Decimal('2.99')
        return self.total_amount + DELIVERY_FEE

    @property
    def total_items_count(self) -> int:
        """Computed property: total number of distinct items in the order."""
        return len(self.items)

    @property
    def total_quantity(self) -> int:
        """Computed property: sum of all quantities in the order."""
        return sum(item.quantity for item in self.items)

# --- Database Storage ---
menu_db: Dict[int, FoodItem] = {}
orders_db: Dict[int, Order] = {}

# Auto-incrementing IDs
next_menu_id = 1
next_order_id = 1

# Helper to add food items to the "database"
def add_food_item_to_db(item_data: FoodItemCreate) -> FoodItem:
    global next_menu_id
    new_item = FoodItem(id=next_menu_id, **item_data.dict())
    menu_db[next_menu_id] = new_item
    next_menu_id += 1
    return new_item

# Populate with sample FoodItem data (from Problem 1)
sample_food_items_raw = [
    {
        "name": "Margherita Pizza",
        "description": "Classic Pizza with tomato sauce, mozzarella cheese, and fresh basil",
        "category": "main_course",
        "price": "15.99",
        "preparation_time": 20,
        "ingredients": ["pizza dough", "tomato sauce", "mozzarella", "basil", "olive oil"],
        "calories": 650,
        "is_vegetarian": True,
        "is_spicy": False
    },
    {
        "name": "Spicy Chicken Wings",
        "description": "Crispy chicken wings tossed in our signature hot sauce",
        "category": "appetizer",
        "price": "12.50",
        "preparation_time": 15,
        "ingredients": ["chicken wings", "hot sauce", "butter", "celery salt"],
        "calories": 420,
        "is_vegetarian": False,
        "is_spicy": True
    },
    {
        "name": "Caesar Salad",
        "description": "Fresh romaine lettuce, croutons, parmesan cheese, and Caesar dressing",
        "category": "salad",
        "price": "8.75",
        "preparation_time": 10,
        "ingredients": ["romaine lettuce", "croutons", "parmesan cheese", "Caesar dressing"],
        "calories": 300,
        "is_vegetarian": True,
        "is_spicy": False
    },
    {
        "name": "Chocolate Lava Cake",
        "description": "Warm chocolate cake with a molten chocolate center, served with vanilla ice cream",
        "category": "dessert",
        "price": "7.99",
        "preparation_time": 25,
        "ingredients": ["chocolate", "flour", "sugar", "eggs", "butter", "ice cream"],
        "calories": 750,
        "is_vegetarian": True,
        "is_spicy": False
    },
    {
        "name": "Orange Juice",
        "description": "Freshly squeezed orange juice",
        "category": "beverage",
        "price": "3.50",
        "preparation_time": 5,
        "ingredients": ["oranges"],
        "calories": 120,
        "is_vegetarian": True,
        "is_spicy": False
    },
    { # Add an item that is currently unavailable for testing purposes
        "name": "Seasonal Soup",
        "description": "Hearty soup available only in winter",
        "category": "appetizer",
        "price": "6.00",
        "preparation_time": 10,
        "ingredients": ["vegetables", "broth"],
        "is_available": False,
        "calories": 250,
        "is_vegetarian": True,
        "is_spicy": False
    }
]

for item_data in sample_food_items_raw:
    item_data_copy = item_data.copy()
    item_data_copy['price'] = Decimal(item_data_copy['price'])
    add_food_item_to_db(FoodItemCreate(**item_data_copy))


# --- FastAPI App Setup ---

app = FastAPI(
    title="Restaurant Ordering System",
    description="API for managing restaurant menu and orders",
    version="1.0.0"
)

# --- Problem 1 Endpoints (Integrated) ---

@app.get("/", summary="Welcome to the Restaurant API")
async def read_root():
    """
    Welcome message for the Restaurant API.
    """
    return {"message": "Welcome to the Restaurant API! Use /docs for interactive documentation."}

@app.post("/menu", response_model=FoodItem, status_code=status.HTTP_201_CREATED, summary="Add a new menu item")
async def add_menu_item(item: FoodItemCreate):
    """
    Add a new food item to the menu. The item ID will be auto-generated.
    - **item**: FoodItemCreate object containing new item details.
    """
    new_item = add_food_item_to_db(item)
    return new_item

@app.get("/menu", response_model=List[FoodItem], summary="Get all menu items")
async def get_all_menu_items():
    """
    Retrieve a list of all food items available on the menu.
    """
    return list(menu_db.values())

@app.get("/menu/{item_id}", response_model=FoodItem, summary="Get specific menu item by ID")
async def get_menu_item(item_id: int):
    """
    Retrieve details of a specific food item using its unique ID.
    - **item_id**: The unique identifier of the food item.
    """
    if item_id not in menu_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Food item not found")
    return menu_db[item_id]

@app.put("/menu/{item_id}", response_model=FoodItem, summary="Update an existing menu item")
async def update_menu_item(item_id: int, updated_item: FoodItemCreate):
    """
    Update an existing food item's details using its unique ID.
    - **item_id**: The unique identifier of the food item to update.
    - **updated_item**: FoodItemCreate object with updated details.
    """
    if item_id not in menu_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Food item not found")

    existing_item_data = menu_db[item_id].dict()
    for field, value in updated_item.dict(exclude_unset=True).items():
        existing_item_data[field] = value
    
    try:
        re_validated_item = FoodItem(id=item_id, **existing_item_data)
        menu_db[item_id] = re_validated_item
        return re_validated_item
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Validation error during update: {e}"
        )

@app.delete("/menu/{item_id}", summary="Remove a menu item")
async def delete_menu_item(item_id: int):
    """
    Remove a food item from the menu using its unique ID.
    - **item_id**: The unique identifier of the food item to remove.
    """
    if item_id not in menu_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Food item not found")
    del menu_db[item_id]
    return {"message": "Food item deleted successfully"}

@app.get("/menu/category/{category}", response_model=List[FoodItem], summary="Get menu items by category")
async def get_items_by_category(category: FoodCategory):
    """
    Retrieve a list of food items belonging to a specific category.
    - **category**: The FoodCategory enum value to filter by.
    """
    filtered_items = [item for item in menu_db.values() if item.category == category]
    if not filtered_items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No items found in category '{category.value}'")
    return filtered_items


# --- Problem 2 Endpoints ---

class FoodItemResponse(BaseModel):
    """
    Response model for returning food items.
    """
    id: int
    name: str
    description: str
    category: FoodCategory
    price: Decimal
    is_available: bool
    preparation_time: int
    ingredients: List[str]
    calories: Optional[int]
    is_vegetarian: bool
    is_spicy: bool

class OrderSummaryResponse(BaseModel):
    """
    Response model for listing orders.
    """
    id: int
    customer_name: str
    total_amount: Decimal
    status: OrderStatus

class OrderResponse(BaseModel):
    """
    Response model for returning detailed order information.
    """
    id: int
    customer: Customer
    items: List[OrderItem]
    total_amount: Decimal
    total_amount_with_delivery: Decimal
    total_items_count: int
    total_quantity: int
    status: OrderStatus

class ErrorResponse(BaseModel):
    """
    Response model for error messages.
    """
    detail: str

@app.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED, summary="Create a new order")
async def create_order(order_data: OrderCreate):
    """
    Create a new customer order.
    - **order_data**: OrderCreate object containing customer info and list of items.
    """
    global next_order_id

    # Validation for OrderCreate (already handled by Pydantic model validation)
    new_order = Order(id=next_order_id, status=OrderStatus.PENDING, **order_data.dict())
    orders_db[next_order_id] = new_order
    next_order_id += 1

    return new_order

@app.get("/orders", response_model=List[OrderSummaryResponse], summary="Get all orders")
async def get_all_orders():
    """
    Retrieve a list of all customer orders.
    """
    return [
        OrderSummaryResponse(
            id=order.id,
            customer_name=order.customer.name,
            total_amount=order.total_amount,
            status=order.status
        )
        for order in orders_db.values()
    ]

@app.get("/orders/{order_id}", response_model=OrderResponse, summary="Get specific order details")
async def get_order_details(order_id: int):
    """
    Retrieve details of a specific order using its unique ID.
    - **order_id**: The unique identifier of the order.
    """
    if order_id not in orders_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return orders_db[order_id]

@app.put("/orders/{order_id}/status", response_model=OrderResponse, summary="Update order status")
async def update_order_status(order_id: int, new_status: OrderStatus = Query(..., description="New status for the order")):
    """
    Update the status of an existing order.
    - **order_id**: The unique identifier of the order to update.
    - **new_status**: The new status to set for the order (e.g., "confirmed", "ready", "delivered").
    """
    if order_id not in orders_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = orders_db[order_id]
    order.status = new_status
    orders_db[order_id] = order
    return order

# --- Test Cases (Demonstrations) ---

@app.get("/run-order-tests", summary="Run various order creation and update test cases")
async def run_order_test_cases():
    """
    This endpoint runs various test cases to demonstrate order creation,
    including valid, invalid, and status updates.
    """
    results = {}

    # Test Case 1: Valid Order
    valid_order_payload = {
        "customer": {
            "name": "Alice Smith",
            "phone": "5551234567",
            "address": "123 Oak Street, Springfield"
        },
        "items": [
            {"menu_item_id": 1, "menu_item_name": "Margherita Pizza", "quantity": 1, "unit_price": "15.99"},
            {"menu_item_id": 2, "menu_item_name": "Spicy Chicken Wings", "quantity": 2, "unit_price": "12.50"}
        ]
    }
    try:
        response = await create_order(OrderCreate(**valid_order_payload))
        results["valid_order_test"] = {"status": "PASS", "order_id": response.id, "details": response.dict()}
        
        # Verify computed properties for the sample order (as in problem description)
        if response.id == 1: # Assuming it's the first order
            assert response.total_amount == Decimal("40.99") # 15.99 + (2 * 12.50) = 15.99 + 25.00 = 40.99
            assert response.total_amount_with_delivery == Decimal("43.98") # 40.99 + 2.99
            assert response.total_items_count == 2
            assert response.total_quantity == 3
            results["valid_order_test"]["computed_properties_verified"] = "PASS"
        else:
            results["valid_order_test"]["computed_properties_verified"] = "SKIPPED (not first order)"

    except HTTPException as e:
        results["valid_order_test"] = {"status": "FAIL", "message": f"Unexpected HTTP error: {e.detail}"}
    except ValueError as e:
        results["valid_order_test"] = {"status": "FAIL", "message": f"Unexpected validation error: {e}"}

    # Test Case 2: Empty Items
    empty_items_payload = {
        "customer": {
            "name": "Bob Johnson",
            "phone": "5559876543",
            "address": "456 Pine Ave"
        },
        "items": []
    }
    try:
        await create_order(OrderCreate(**empty_items_payload))
        results["empty_items_test"] = {"status": "FAIL", "message": "Order with empty items should have failed."}
    except HTTPException as e:
        results["empty_items_test"] = {"status": "PASS", "message": e.detail}
    except ValueError as e:
        results["empty_items_test"] = {"status": "PASS", "message": str(e)}

    # Test Case 3: Invalid Phone
    invalid_phone_payload = {
        "customer": {
            "name": "Charlie Brown",
            "phone": "123", # Invalid phone
            "address": "789 Cedar Rd"
        },
        "items": [
            {"menu_item_id": 3, "menu_item_name": "Caesar Salad", "quantity": 1, "unit_price": "8.75"}
        ]
    }
    try:
        await create_order(OrderCreate(**invalid_phone_payload))
        results["invalid_phone_test"] = {"status": "FAIL", "message": "Order with invalid phone should have failed."}
    except HTTPException as e:
        results["invalid_phone_test"] = {"status": "PASS", "message": e.detail}
    except ValueError as e: # Pydantic ValueError if regex fails before HTTPException
        results["invalid_phone_test"] = {"status": "PASS", "message": str(e)}

    # Test Case 4: Large Quantity (max is 10)
    large_quantity_payload = {
        "customer": {
            "name": "Diana Prince",
            "phone": "5551112222",
            "address": "101 Paradise Island"
        },
        "items": [
            {"menu_item_id": 4, "menu_item_name": "Chocolate Lava Cake", "quantity": 15, "unit_price": "7.99"} # Quantity > 10
        ]
    }
    try:
        await create_order(OrderCreate(**large_quantity_payload))
        results["large_quantity_test"] = {"status": "FAIL", "message": "Order with large quantity should have failed."}
    except HTTPException as e:
        results["large_quantity_test"] = {"status": "PASS", "message": e.detail}
    except ValueError as e:
        results["large_quantity_test"] = {"status": "PASS", "message": str(e)}

    # Test Case 5: Status Update
    # First, ensure a valid order exists (from Test Case 1)
    if "valid_order_test" in results and results["valid_order_test"]["status"] == "PASS":
        order_id_to_update = results["valid_order_test"]["order_id"]
        try:
            updated_order = await update_order_status(order_id_to_update, OrderStatus.CONFIRMED)
            if updated_order.status == OrderStatus.CONFIRMED:
                results["status_update_test"] = {"status": "PASS", "new_status": updated_order.status}
            else:
                results["status_update_test"] = {"status": "FAIL", "message": "Status not updated correctly."}
        except HTTPException as e:
            results["status_update_test"] = {"status": "FAIL", "message": f"HTTP error during status update: {e.detail}"}
    else:
        results["status_update_test"] = {"status": "SKIPPED", "message": "Valid order not created for update test."}

    # Test Case 6: Invalid menu_item_id
    invalid_menu_item_id_payload = {
        "customer": {
            "name": "Eve Adams",
            "phone": "5553334444",
            "address": "789 Fake Street"
        },
        "items": [
            {"menu_item_id": 999, "menu_item_name": "Non Existent", "quantity": 1, "unit_price": "10.00"} # ID 999 does not exist
        ]
    }
    try:
        await create_order(OrderCreate(**invalid_menu_item_id_payload))
        results["invalid_menu_item_id_test"] = {"status": "FAIL", "message": "Order with non-existent menu item should have failed."}
    except HTTPException as e:
        results["invalid_menu_item_id_test"] = {"status": "PASS", "message": e.detail}
    except ValueError as e:
        results["invalid_menu_item_id_test"] = {"status": "PASS", "message": str(e)}

    # Test Case 7: Price Mismatch (client price vs menu price)
    price_mismatch_payload = {
        "customer": {
            "name": "Frank Green",
            "phone": "5555556666",
            "address": "888 Discount Lane"
        },
        "items": [
            {"menu_item_id": 1, "menu_item_name": "Margherita Pizza", "quantity": 1, "unit_price": "10.00"} # Margherita is 15.99
        ]
    }
    try:
        await create_order(OrderCreate(**price_mismatch_payload))
        results["price_mismatch_test"] = {"status": "FAIL", "message": "Order with price mismatch should have failed."}
    except HTTPException as e:
        results["price_mismatch_test"] = {"status": "PASS", "message": e.detail}
    except ValueError as e:
        results["price_mismatch_test"] = {"status": "PASS", "message": str(e)}
        
    # Test Case 8: Unavailable menu item
    unavailable_item_payload = {
        "customer": {
            "name": "Grace Hopper",
            "phone": "1234567890",
            "address": "Code Alley"
        },
        "items": [
            {"menu_item_id": 6, "menu_item_name": "Seasonal Soup", "quantity": 1, "unit_price": "6.00"} # Seasonal Soup is not available
        ]
    }
    try:
        await create_order(OrderCreate(**unavailable_item_payload))
        results["unavailable_item_test"] = {"status": "FAIL", "message": "Order with unavailable item should have failed."}
    except HTTPException as e:
        results["unavailable_item_test"] = {"status": "PASS", "message": e.detail}
    except ValueError as e:
        results["unavailable_item_test"] = {"status": "PASS", "message": str(e)}

    return results

# Example structure for menu_db and orders_db (already defined globally)
# menu_db: Dict[int, FoodItem] = {}
# orders_db: Dict[int, Order] = {}

# Auto-incrementing IDs (already defined globally)
# next_menu_id = 1
# next_order_id = 1

# To run the application:
# 1. Save the code as main.py
# 2. Install FastAPI and Uvicorn: pip install fastapi "uvicorn[standard]"
# 3. Run from your terminal: uvicorn main:app --reload
# 4. Access your browser at http://127.0.0.1:8000/docs for the interactive API documentation.
# 5. Access http://127.0.0.1:8000/run-order-tests to see the validation test case results.