from fastapi import FastAPI, Request, Depends, Form, HTTPException, status, Cookie
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
import uvicorn
from datetime import datetime, date
from typing import Optional
import bcrypt

# Import models & database
from models import Base, Store, Category, Product, Customer, Order, OrderItem, OrderStatus, User, UserRole
from database import engine, get_db

app = FastAPI(title="POS SaaS System")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Tengeneza meza zote kiotomatiki
Base.metadata.create_all(bind=engine)


# ==========================================
# UTILITY & AUTH HELPER FUNCTIONS
# ==========================================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'), 
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def get_object_or_404(model, db: Session, obj_id: int):
    obj = db.query(model).filter(model.id == obj_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Kipengele hakipatikani")
    return obj

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    user_id = request.cookies.get("user_id")
    if not user_id:
        return None
    try:
        user = db.query(User).filter(User.id == int(user_id), User.is_active == True).first()
        return user
    except Exception:
        return None

def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user or user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Huna ruhusa ya kufikia eneo hili")
    return user


# ==========================================
# AUTHENTICATION ROUTES (LOGIN / REGISTER / LOGOUT)
# ==========================================
@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Username au Password sio sahihi"}
        )
    
    if not user.is_active:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Akaunti hii imefungwa. Wasiliana na Admin."}
        )

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="user_id", value=str(user.id), httponly=True)
    return response

@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html")

@app.post("/register")
def register(
    request: Request,
    store_name: str = Form(...),
    username: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "Username hii tayari inatumika!"}
        )
    
    # 1. Tengeneza Duka Jipya la Mmiliki
    new_store = Store(name=store_name)
    db.add(new_store)
    db.flush() # Ili kupata ID ya duka hili mpya
    
    # 2. Mtengenezee mtumiaji na umfanye ADMIN wa duka lake
    new_user = User(
        store_id=new_store.id,
        username=username,
        full_name=full_name,
        hashed_password=hash_password(password),
        role=UserRole.ADMIN,
        is_active=True
    )
    db.add(new_user)
    db.commit()

    return RedirectResponse(url="/login?success=Account created successfully", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="user_id")
    return response


# ==========================================
# USER MANAGEMENT (CRUD FOR ADMIN ONLY)
# ==========================================
@app.get("/users")
def list_users(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    users = db.query(User).filter(User.store_id == current_user.store_id).all()
    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={"users": users, "current_user": current_user}
    )

@app.get("/users/add")
def add_user_form(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return templates.TemplateResponse(
        request=request,
        name="add_user.html",
        context={"roles": [r.value for r in UserRole], "current_user": current_user}
    )

@app.post("/users/add")
def add_user(
    username: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username hii tayari imeshatumika")

    new_user = User(
        store_id=admin.store_id, # Wafanyakazi wanaunganishwa kwenye duka la Admin huyu
        username=username,
        full_name=full_name,
        hashed_password=hash_password(password),
        role=UserRole[role] if role in UserRole.__members__ else UserRole.CASHIER,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/users/edit/{user_id}")
def edit_user_form(request: Request, user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    target_user = get_object_or_404(User, db, user_id)
    if target_user.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
    return templates.TemplateResponse(
        request=request,
        name="add_user.html",
        context={
            "target_user": target_user,
            "roles": [r.value for r in UserRole],
            "current_user": current_user
        }
    )

@app.post("/users/edit/{user_id}")
def edit_user(
    user_id: int,
    username: str = Form(...),
    full_name: str = Form(...),
    role: str = Form(...),
    password: Optional[str] = Form(None),
    is_active: bool = Form(True),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    target_user = get_object_or_404(User, db, user_id)
    if target_user.store_id != admin.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    target_user.username = username
    target_user.full_name = full_name
    if role in UserRole.__members__:
        target_user.role = UserRole[role]
    target_user.is_active = is_active

    if password and password.strip() != "":
        target_user.hashed_password = hash_password(password)

    db.commit()
    return RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/users/delete/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    target_user = get_object_or_404(User, db, user_id)
    if target_user.store_id != admin.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
    db.delete(target_user)
    db.commit()
    return RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)


# ==========================================
# DASHBOARD
# ==========================================
@app.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    today_orders = db.query(Order).filter(
        Order.store_id == current_user.store_id,
        Order.status == OrderStatus.COMPLETED
    ).all()
    
    today_sales = 0.0
    today_cogs = 0.0
    
    for order in today_orders:
        today_sales += order.total_amount
        for item in order.order_items:
            product_cost = item.product.cost_price if item.product and item.product.cost_price else 0.0
            today_cogs += (product_cost * item.quantity)
            
    today_profit = today_sales - today_cogs
    
    low_stock_count = db.query(Product).filter(
        Product.store_id == current_user.store_id,
        Product.quantity <= Product.min_stock_level
    ).count()
    
    recent_orders = db.query(Order).filter(Order.store_id == current_user.store_id).order_by(Order.created_at.desc()).limit(10).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "today_sales": today_sales,
            "today_profit": today_profit,
            "today_orders_count": len(today_orders),
            "low_stock_count": low_stock_count,
            "orders": recent_orders,
            "current_user": current_user
        }
    )


# ==========================================
# CATEGORIES CRUD
# ==========================================
@app.get("/categories")
def list_categories(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    categories = db.query(Category).filter(Category.store_id == current_user.store_id).all()
    return templates.TemplateResponse(
        request=request,
        name="categories.html",
        context={"categories": categories, "current_user": current_user}
    )

@app.get("/categories/add")
def add_category_form(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="add_category.html",
        context={"current_user": current_user}
    )

@app.post("/categories/add")
def add_category(name: str = Form(...), description: str = Form(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    cat = Category(store_id=current_user.store_id, name=name, description=description)
    db.add(cat)
    db.commit()
    return RedirectResponse(url="/categories", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/categories/edit/{category_id}")
def edit_category_form(request: Request, category_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    category = get_object_or_404(Category, db, category_id)
    if category.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    return templates.TemplateResponse(
        request=request,
        name="add_category.html",
        context={"category": category, "current_user": current_user}
    )

@app.post("/categories/edit/{category_id}")
def edit_category(category_id: int, name: str = Form(...), description: str = Form(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    category = get_object_or_404(Category, db, category_id)
    if category.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    category.name = name
    category.description = description
    db.commit()
    return RedirectResponse(url="/categories", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/categories/delete/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    category = get_object_or_404(Category, db, category_id)
    if category.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    db.delete(category)
    db.commit()
    return RedirectResponse(url="/categories", status_code=status.HTTP_303_SEE_OTHER)


# ==========================================
# PRODUCTS CRUD & INVENTORY
# ==========================================
@app.get("/products")
async def products(request: Request, q: str = None, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    query = db.query(Product).filter(Product.store_id == current_user.store_id)
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
        
    products_list = query.all()
    categories = db.query(Category).filter(Category.store_id == current_user.store_id).all()
    
    return templates.TemplateResponse(
        request=request,
        name="products.html",
        context={
            "products": products_list,
            "categories": categories,
            "q": q,
            "current_user": current_user
        }
    )

@app.get("/products/add")
def add_product_form(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    categories = db.query(Category).filter(Category.store_id == current_user.store_id).all()
    return templates.TemplateResponse(
        request=request,
        name="add_product.html",
        context={"categories": categories, "current_user": current_user}
    )

@app.post("/products/add")
def add_product(
    name: str = Form(...), 
    cost_price: float = Form(0.0),
    price: float = Form(...), 
    quantity: int = Form(...),
    min_stock_level: int = Form(5),
    category_id: int = Form(...), 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    product = Product(
        store_id=current_user.store_id,
        name=name, 
        cost_price=cost_price,
        price=price, 
        quantity=quantity, 
        min_stock_level=min_stock_level,
        category_id=category_id
    )
    db.add(product)
    db.commit()
    return RedirectResponse(url="/products", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/products/edit/{product_id}")
def edit_product_form(request: Request, product_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    product = get_object_or_404(Product, db, product_id)
    if product.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    categories = db.query(Category).filter(Category.store_id == current_user.store_id).all()
    return templates.TemplateResponse(
        request=request,
        name="add_product.html",
        context={"product": product, "categories": categories, "current_user": current_user}
    )

@app.post("/products/edit/{product_id}")
def edit_product(
    product_id: int, 
    name: str = Form(...), 
    cost_price: float = Form(0.0),
    price: float = Form(...), 
    quantity: int = Form(...),
    min_stock_level: int = Form(5),
    category_id: int = Form(...), 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    product = get_object_or_404(Product, db, product_id)
    if product.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    product.name = name
    product.cost_price = cost_price
    product.price = price
    product.quantity = quantity
    product.min_stock_level = min_stock_level
    product.category_id = category_id
    db.commit()
    return RedirectResponse(url="/products", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/products/delete/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    product = get_object_or_404(Product, db, product_id)
    if product.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    db.delete(product)
    db.commit()
    return RedirectResponse(url="/products", status_code=status.HTTP_303_SEE_OTHER)


# ==========================================
# INVENTORY: RESTOCK & LOW STOCK ALERTS
# ==========================================
@app.post("/products/restock/{product_id}")
def restock_product(
    product_id: int, 
    added_quantity: int = Form(...), 
    new_cost_price: float = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    product = get_object_or_404(Product, db, product_id)
    if product.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    if added_quantity <= 0:
        raise HTTPException(status_code=400, detail="Idadi ya kuongeza lazima iwe zaidi ya 0")
        
    product.quantity += added_quantity
    if new_cost_price and new_cost_price > 0:
        product.cost_price = new_cost_price
        
    db.commit()
    return RedirectResponse(url="/inventory/low-stock", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/inventory/low-stock")
def low_stock_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    low_stock_products = db.query(Product).filter(
        Product.store_id == current_user.store_id,
        Product.quantity <= Product.min_stock_level
    ).all()
    
    return templates.TemplateResponse(
        request=request,
        name="low_stock.html",
        context={"products": low_stock_products, "current_user": current_user}
    )


# ==========================================
# CUSTOMERS & DEBTS
# ==========================================
@app.get("/customers")
def list_customers(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    customers = db.query(Customer).filter(Customer.store_id == current_user.store_id).all()
    return templates.TemplateResponse(
        request=request,
        name="customers.html",
        context={"customers": customers, "current_user": current_user}
    )

@app.get("/customers/add")
def add_customer_form(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="add_customer.html",
        context={"current_user": current_user}
    )

@app.post("/customers/add")
def add_customer(name: str = Form(...), email: str = Form(None), phone: str = Form(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = Customer(
        store_id=current_user.store_id,
        name=name, 
        email=email, 
        phone=phone, 
        current_balance=0.0
    )
    db.add(customer)
    db.commit()
    return RedirectResponse(url="/customers", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/customers/edit/{customer_id}")
def edit_customer_form(request: Request, customer_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    customer = get_object_or_404(Customer, db, customer_id)
    if customer.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    return templates.TemplateResponse(
        request=request,
        name="add_customer.html",
        context={"customer": customer, "current_user": current_user}
    )

@app.post("/customers/edit/{customer_id}")
def edit_customer(customer_id: int, name: str = Form(...), email: str = Form(None), phone: str = Form(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = get_object_or_404(Customer, db, customer_id)
    if customer.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    customer.name = name
    customer.email = email
    customer.phone = phone
    db.commit()
    return RedirectResponse(url="/customers", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/customers/delete/{customer_id}")
def delete_customer(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer = get_object_or_404(Customer, db, customer_id)
    if customer.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    db.delete(customer)
    db.commit()
    return RedirectResponse(url="/customers", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/customers/debts")
def customer_debts_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    customers_with_debts = db.query(Customer).filter(
        Customer.store_id == current_user.store_id,
        Customer.current_balance > 0
    ).all()
    
    return templates.TemplateResponse(
        request=request,
        name="customer_debts.html",
        context={"customers": customers_with_debts, "current_user": current_user}
    )

@app.post("/customers/{customer_id}/pay-debt")
async def pay_customer_debt(
    customer_id: int, 
    amount_paid: float = Form(...), 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    customer = get_object_or_404(Customer, db, customer_id)
    if customer.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    customer.current_balance -= amount_paid
    if customer.current_balance < 0:
        customer.current_balance = 0.0

    db.commit()
    return RedirectResponse(url="/customers/debts", status_code=303)


# ==========================================
# ORDERS & SALES
# ==========================================
@app.get("/orders/create")
def create_order_form(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    customers = db.query(Customer).filter(Customer.store_id == current_user.store_id).all()
    products = db.query(Product).filter(Product.store_id == current_user.store_id, Product.quantity > 0).all()
    return templates.TemplateResponse(
        request=request,
        name="create_order.html",
        context={"customers": customers, "products": products, "current_user": current_user}
    )

@app.post("/orders/create")
async def create_order(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        raise HTTPException(status_code=401, detail="Haujajitambulisha")
        
    data = await request.json()
    customer_id = data.get("customer_id")
    items = data.get("items")
    amount_paid = float(data.get("amount_paid", 0.0))
    payment_method = data.get("payment_method", "CASH")

    if not items or len(items) == 0:
        raise HTTPException(status_code=400, detail="Hujaweka bidhaa yoyote kwenye kikapu")

    if payment_method == "CREDIT" and not customer_id:
        raise HTTPException(status_code=400, detail="Huwezi kuuza kwa mkopo bila kumchagua mteja husika")

    total_amount = 0.0
    order_items_to_save = []

    try:
        for item in items:
            product = db.query(Product).filter(Product.id == item["product_id"], Product.store_id == current_user.store_id).first()
            if not product:
                raise HTTPException(status_code=404, detail="Bidhaa haipatikani kwenye duka lako")

            qty = int(item["quantity"])
            if product.quantity < qty:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Stoki ya '{product.name}' haitoshi! Imebaki {product.quantity}"
                )

            subtotal = product.price * qty
            total_amount += subtotal
            product.quantity -= qty

            order_items_to_save.append({
                "product_id": product.id,
                "quantity": qty,
                "price": product.price,
                "subtotal": subtotal
            })

        if payment_method == "CASH" and amount_paid < total_amount:
            raise HTTPException(
                status_code=400, 
                detail=f"Kiasi kilicholipwa ni kidogo kuliko jumla ya mauzo"
            )

        change_given = amount_paid - total_amount if payment_method == "CASH" else 0.0

        new_order = Order(
            store_id=current_user.store_id, # <--- Muhimu sana
            customer_id=customer_id if customer_id else None,
            user_id=current_user.id,
            total_amount=total_amount,
            status=OrderStatus.COMPLETED
        )
        db.add(new_order)
        db.flush()

        for item_data in order_items_to_save:
            order_item = OrderItem(
                order_id=new_order.id,
                product_id=item_data["product_id"],
                quantity=item_data["quantity"],
                price=item_data["price"],
                subtotal=item_data["subtotal"]
            )
            db.add(order_item)

        if payment_method == "CREDIT" and customer_id:
            customer = db.query(Customer).filter(Customer.id == customer_id, Customer.store_id == current_user.store_id).first()
            if customer:
                customer.current_balance = (customer.current_balance or 0.0) + total_amount

        db.commit()

        return {
            "message": "Mauzo yamekamilika!", 
            "order_id": new_order.id,
            "total_amount": total_amount,
            "amount_paid": amount_paid,
            "change": change_given
        }

    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Hitilafu imetokea: {str(e)}")

@app.get("/orders/receipt/{order_id}")
def view_receipt(request: Request, order_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    order = get_object_or_404(Order, db, order_id)
    if order.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    return templates.TemplateResponse(
        request=request,
        name="receipt.html",
        context={"order": order, "current_user": current_user}
    )

@app.post("/orders/{order_id}/status")
def update_order_status(order_id: int, new_status: str = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = get_object_or_404(Order, db, order_id)
    if order.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    if new_status in OrderStatus.__members__:
        order.status = OrderStatus[new_status]
        db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/orders/delete/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    order = get_object_or_404(Order, db, order_id)
    if order.store_id != admin.store_id:
        raise HTTPException(status_code=403, detail="Huna ruhusa")
        
    try:
        for item in order.order_items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if product:
                product.quantity += item.quantity
                
        db.delete(order)
        db.commit()
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Imeshindikana kufuta oda: {str(e)}")


# ==========================================
# REPORTS (PROFIT & LOSS)
# ==========================================
@app.get("/reports/profit-loss")
def profit_loss_report(
    request: Request, 
    start_date: str = None, 
    end_date: str = None, 
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    query = db.query(Order).filter(
        Order.store_id == current_user.store_id,
        Order.status == OrderStatus.COMPLETED
    )
    
    if start_date:
        query = query.filter(Order.created_at >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        query = query.filter(Order.created_at <= end_dt)
        
    completed_orders = query.all()
    
    total_revenue = 0.0
    total_cogs = 0.0
    total_items_sold = 0
    
    for order in completed_orders:
        total_revenue += order.total_amount
        for item in order.order_items:
            total_items_sold += item.quantity
            product_cost = item.product.cost_price if item.product and item.product.cost_price else 0.0
            total_cogs += (product_cost * item.quantity)
            
    net_profit = total_revenue - total_cogs
    
    return templates.TemplateResponse(
        request=request,
        name="profit_loss.html",
        context={
            "orders": completed_orders,
            "total_revenue": total_revenue,
            "total_cogs": total_cogs,
            "net_profit": net_profit,
            "total_items_sold": total_items_sold,
            "start_date": start_date or "",
            "end_date": end_date or "",
            "current_user": current_user
        }
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
