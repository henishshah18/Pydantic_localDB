import uvicorn
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import List, Optional, Dict
from decimal import Decimal
import re

# 1. Data Model Requirements

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

    # Custom Validations
    @field_validator('name')
    def validate_name_characters(cls, v):
        """Name should not contain numbers or special characters (only letters and spaces)."""
        if not re.fullmatch(r'^[a-zA-Z\s]+$', v):
            raise ValueError('Name should only contain letters and spaces')
        return v.strip()

    @field_validator('price')
    def validate_price_range(cls, v):
        """Price should be between $1.00 and $100.00."""
        if not (Decimal('1.00') <= v <= Decimal('100.00')):
            raise ValueError('Price must be between $1.00 and $100.00')
        return v

    # Computed Properties
    @property
    def price_category(self) -> str:
        """Returns price category: "Budget" (<$10), "Mid-range" ($10-25), "Premium" (>$25)."""
        if self.price < Decimal('10.00'):
            return "Budget"
        elif Decimal('10.00') <= self.price <= Decimal('25.00'):
            return "Mid-range"
        else:
            return "Premium"

    @property
    def dietary_info(self) -> List[str]:
        """Returns a list like ["Vegetarian", "Spicy"] based on flags."""
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

# 2. Database Storage
menu_db: Dict[int, FoodItem] = {}
last_item_id = 0

# FastAPI app instance
app = FastAPI(title="Restaurant Food Ordering System API")

# Helper to add items to the "database"
def add_item_to_db(item_data: FoodItemCreate) -> FoodItem:
    global last_item_id
    last_item_id += 1
    new_item = FoodItem(id=last_item_id, **item_data.dict())
    menu_db[last_item_id] = new_item
    return new_item

# Populate with sample data
sample_menu_items_raw = [
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
    # Add 3 more items as required by the problem statement
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
    }
]

# Convert price strings to Decimal and add sample data to the database
for item_data in sample_menu_items_raw:
    item_data_copy = item_data.copy() # Avoid modifying the original dict during iteration
    item_data_copy['price'] = Decimal(item_data_copy['price'])
    add_item_to_db(FoodItemCreate(**item_data_copy))


# 3. API Endpoints Required

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

@app.post("/menu", response_model=FoodItem, status_code=status.HTTP_201_CREATED, summary="Add a new menu item")
async def add_menu_item(item: FoodItemCreate):
    """
    Add a new food item to the menu. The item ID will be auto-generated.
    - **item**: FoodItemCreate object containing new item details.
    """
    new_item = add_item_to_db(item)
    return new_item

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
    # Update fields from updated_item
    for field, value in updated_item.dict(exclude_unset=True).items():
        existing_item_data[field] = value
    
    try:
        # Create a new FoodItem instance to trigger all validations, including root_validator
        re_validated_item = FoodItem(id=item_id, **existing_item_data) 
        menu_db[item_id] = re_validated_item # Store the re-validated item
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

# 4. Test Cases to Handle (Demonstrations)
@app.get("/test-cases", summary="Demonstrate FoodItem validation test cases")
async def run_test_cases():
    """
    This endpoint runs various test cases to demonstrate custom validations
    of the FoodItemCreate model.
    """
    results = {}

    # Test Case 1: Valid Data (already added as sample)
    results["valid_data_example"] = sample_menu_items_raw[0]

    # Test Case 2: Invalid Price: Try to create item with price $0.50 (should fail)
    try:
        invalid_price_item = FoodItemCreate(
            name="Tiny Snack",
            description="A very tiny snack for a very tiny price",
            category=FoodCategory.APPETIZER,
            price=Decimal("0.50"),
            preparation_time=5,
            ingredients=["bread", "butter"]
        )
        results["invalid_price_test"] = {"status": "FAIL", "message": "Should have failed due to invalid price range."}
    except ValueError as e:
        results["invalid_price_test"] = {"status": "PASS", "message": str(e)}

    # Test Case 3: Invalid Category: Try to mark a beverage as spicy (should fail)
    try:
        invalid_category_spicy_item = FoodItemCreate(
            name="Spicy Lemonade",
            description="Lemonade with a kick!",
            category=FoodCategory.BEVERAGE,
            price=Decimal("4.00"),
            preparation_time=5,
            ingredients=["lemon", "sugar", "water", "chili"],
            is_spicy=True
        )
        results["invalid_category_spicy_test"] = {"status": "FAIL", "message": "Should have failed: beverage cannot be spicy."}
    except ValueError as e:
        results["invalid_category_spicy_test"] = {"status": "PASS", "message": str(e)}

    # Test Case 4: Missing Ingredients: Try to create item with empty ingredients list
    try:
        missing_ingredients_item = FoodItemCreate(
            name="Empty Dish",
            description="A dish with no ingredients",
            category=FoodCategory.MAIN_COURSE,
            price=Decimal("10.00"),
            preparation_time=10,
            ingredients=[]
        )
        results["missing_ingredients_test"] = {"status": "FAIL", "message": "Should have failed: empty ingredients list."}
    except ValueError as e:
        results["missing_ingredients_test"] = {"status": "PASS", "message": str(e)}

    # Test Case 5: Invalid Name: Try to create item with name "Pizza123!" (should fail)
    try:
        invalid_name_item = FoodItemCreate(
            name="Pizza123!",
            description="Pizza with invalid characters in name",
            category=FoodCategory.MAIN_COURSE,
            price=Decimal("15.00"),
            preparation_time=20,
            ingredients=["dough", "cheese"]
        )
        results["invalid_name_test"] = {"status": "FAIL", "message": "Should have failed due to invalid name characters."}
    except ValueError as e:
        results["invalid_name_test"] = {"status": "PASS", "message": str(e)}
        
    # Additional Test Case: Vegetarian items should have calories < 800 (if calories provided)
    try:
        high_cal_veg_item = FoodItemCreate(
            name="Giant Veggie Burger",
            description="A huge burger for vegetarians",
            category=FoodCategory.MAIN_COURSE,
            price=Decimal("18.00"),
            preparation_time=30,
            ingredients=["patty", "bun", "lettuce"],
            calories=850, # Calories >= 800 for vegetarian
            is_vegetarian=True
        )
        results["high_cal_veg_test"] = {"status": "FAIL", "message": "Should have failed: vegetarian calories >= 800."}
    except ValueError as e:
        results["high_cal_veg_test"] = {"status": "PASS", "message": str(e)}

    # Additional Test Case: Preparation time for beverages should be <= 10 minutes
    try:
        long_prep_beverage = FoodItemCreate(
            name="Slow Brew Coffee",
            description="Coffee that takes a long time to make",
            category=FoodCategory.BEVERAGE,
            price=Decimal("5.00"),
            preparation_time=12, # Prep time > 10 for beverage
            ingredients=["coffee beans", "water"]
        )
        results["long_prep_beverage_test"] = {"status": "FAIL", "message": "Should have failed: beverage prep time > 10 minutes."}
    except ValueError as e:
        results["long_prep_beverage_test"] = {"status": "PASS", "message": str(e)}

    return results

# To run the application:
# 1. Save the code as main.py
# 2. Install FastAPI and Uvicorn: pip install fastapi "uvicorn[standard]"
# 3. Run from your terminal: uvicorn main:app --reload
# 4. Access your browser at http://127.0.0.1:8000/docs for the interactive API documentation.
# 5. Access http://127.0.0.1:8000/test-cases to see the validation test case results.