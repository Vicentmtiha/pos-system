from pydantic import BaseModel
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


import requests

NEXTSMS_API_TOKEN = "WEKA_API_KEY_YAKO_HAPA"

def send_nextsms(phone_number: str, message: str):
    url = "https://messaging-service.co.tz/api/sms/v1/text/single"
    
    headers = {
        "Authorization": f"Bearer {NEXTSMS_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    payload = {
        "from": "INFO", 
        "to": phone_number,
        "text": message
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Hitilafu ya kutuma SMS: {e}")
        return None
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
        store_id=admin.store_id,
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
from pydantic import BaseModel
from fastapi import FastAPI, Request, Depends, Form, HTTPException, status, Cookie, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
import uvicorn
from datetime import datetime, date
from typing import Optional
import bcrypt
import requests
import io
import pandas as pd

# Import models & database
from models import Base, Store, Category, Product, Customer, Order, OrderItem, OrderStatus, User, UserRole
from database import engine, get_db

app = FastAPI(title="POS SaaS System - Full Edition")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Tengeneza meza zote kiotomatiki
Base.metadata.create_all(bind=engine)


# ==========================================
# 1. UTILITY & AUTH HELPER FUNCTIONS
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
        raise HTTPException(status_code=404, detail="Kipengele hakipatikani kwenye mfumo")
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
        raise HTTPException(status_code=403, detail="Huna ruhusa ya kufikia eneo hili la kiutawala")
    return user


NEXTSMS_API_TOKEN = "WEKA_API_KEY_YAKO_HAPA"

def send_nextsms(phone_number: str, message: str):
    url = "https://messaging-service.co.tz/api/sms/v1/text/single"
    headers = {
        "Authorization": f"Bearer {NEXTSMS_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "from": "INFO", 
        "to": phone_number,
        "text": message
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Hitilafu ya kutuma SMS: {e}")
        return None


# ==========================================
# 2. AUTHENTICATION ROUTES (LOGIN / REGISTER / LOGOUT)
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
            context={"error": "Akaunti hii imefungwa. Wasiliana na Admin wako."}
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
            context={"error": "Username hii tayari inatumika na mtu mwingine!"}
        )
    
    new_store = Store(name=store_name)
    db.add(new_store)
    db.flush()
    
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
# 3. USER MANAGEMENT (CRUD FOR ADMIN ONLY)
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
        store_id=admin.store_id,
        username=username,
        full_name=full_name,
        hashed_password=hash_password(password),
        role=UserRole[role] if role in UserRole.__members__ else UserRole.CASHIER,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)


# ==========================================
# 4. DASHBOARD & ANALYTICS
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
# 5. CATEGORIES CRUD
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


# ==========================================
# 6. PRODUCTS & EXCEL UPLOAD
# ==========================================
@app.post("/products/upload-excel")
async def upload_products_excel(file: UploadFile = File(...), db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        return {"error": "Tafadhali pakia faili la Excel au CSV pekee."}
    
    try:
        contents = await file.read()
        if file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            df = pd.read_csv(io.BytesIO(contents))
        
        for _, row in df.iterrows():
            product = Product(
                name=str(row.get('name', 'Bidhaa Mpya')),
                barcode=str(row.get('barcode', '')),
                size=str(row.get('size', '')),
                cost_price=float(row.get('cost_price', 0)),
                price=float(row.get('price', 0)),
                quantity=int(row.get('quantity', 0)),
                min_stock_level=int(row.get('min_stock_level', 5)),
                store_id=current_user.store_id if hasattr(current_user, 'store_id') else 1
            )
            db.add(product)
        db.commit()
    except Exception as e:
        db.rollback()
        return {"error": f"Imetokea hitilafu wakati wa kusoma faili: {str(e)}"}
        
    return {"message": "Bidhaa zote zimeingizwa stoo kwa mafanikio makubwa!"}

@app.get("/products")
async def products(request: Request, q: str = None, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    query = db.query(Product).filter(Product.store_id == current_user.store_id)
    if q:
        query = query.filter(
            (Product.name.ilike(f"%{q}%")) | (Product.barcode.ilike(f"%{q}%")) | (Product.size.ilike(f"%{q}%"))
        )
        
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


# ==========================================
# 7. CUSTOMERS & DEBTS MANAGEMENT
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


# ==========================================
# 8. ORDERS, POS & BARCODE SEARCH API
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

@app.get("/api/products/search")
def api_search_product(barcode: Optional[str] = None, query: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    db_query = db.query(Product).filter(Product.store_id == current_user.store_id)
    
    if barcode:
        product = db_query.filter(Product.barcode == barcode).first()
        if not product:
            raise HTTPException(status_code=404, detail="Bidhaa haijapatikana kwa Barcode hiyo")
        return [{
            "id": product.id,
            "name": product.name,
            "barcode": product.barcode,
            "size": product.size,
            "price": product.price,
            "quantity": product.quantity
        }]
        
    if query:
        products = db_query.filter(
            (Product.name.ilike(f"%{query}%")) | 
            (Product.barcode.ilike(f"%{query}%")) | 
            (Product.size.ilike(f"%{query}%"))
        ).all()
        return [{
            "id": p.id,
            "name": p.name,
            "barcode": p.barcode,
            "size": p.size,
            "price": p.price,
            "quantity": p.quantity
        } for p in products]
        
    return []

@app.get("/orders/receipt/{order_id}")
def view_receipt(request: Request, order_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    order = get_object_or_404(Order, db, order_id)
    return templates.TemplateResponse(request=request, name="receipt.html", context={"order": order, "current_user": current_user})
