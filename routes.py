import os
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, session, url_for
from sqlalchemy import create_engine, text
from datetime import datetime

app = Flask(__name__)
UPLOAD_FOLDER = 'static/images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the directory exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
app.secret_key = "secret123"

engine = create_engine("mysql+pymysql://root:Yohan969$$@localhost/ecommerce")


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = dict(request.form) # Convert to dict to modify

        with engine.connect() as conn:
            # Check duplicate email
            existing = conn.execute(text("SELECT * FROM users WHERE email = :email"), 
                                  {"email": data['email']}).fetchone()
            if existing: return "Email already exists"

            # logic: Customers are approved immediately, others (vendors) are not
            data['is_approved'] = 1 if data['role'] == 'customer' else 0

            conn.execute(text("""
                INSERT INTO users (name, email, username, password, role, is_approved)
                VALUES (:name, :email, :username, :password, :role, :is_approved)
            """), data)
            conn.commit()

        return redirect('/login')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.form
        with engine.connect() as conn:
            user = conn.execute(text("""
                SELECT * FROM users 
                WHERE (email = :login OR username = :login) AND password = :password
            """), {"login": data['login'], "password": data['password']}).fetchone()

            if user:
                if not user.is_approved:
                    return "Your account is pending admin approval."
                
                session['user_id'] = user.id
                session['role'] = user.role
                return redirect('/')

        return "Invalid login"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')









@app.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    user_id = session.get('user_id')
    
    # 1. Safety Check: Is the user logged in?
    if not user_id:
        # Save a message to show the user they need to log in
        return redirect(url_for('login'))

    # 2. Get data from the hidden inputs and dropdowns
    product_id = request.form.get('product_id')
    color_id = request.form.get('color_id')
    size_id = request.form.get('size_id')
    quantity = request.form.get('quantity', 1)

    with engine.begin() as conn:
        # 3. Check if the item already exists in the cart to increment quantity
        # (Optional but recommended for a professional feel)
        existing = conn.execute(text("""
            SELECT id FROM cart_items 
            WHERE user_id = :uid AND product_id = :pid AND color_id = :cid AND size_id = :sid
        """), {"uid": user_id, "pid": product_id, "cid": color_id, "sid": size_id}).fetchone()

        if existing:
            conn.execute(text("""
                UPDATE cart_items SET quantity = quantity + :q 
                WHERE id = :id
            """), {"q": quantity, "id": existing[0]})
        else:
            # 4. Insert new item
            conn.execute(text("""
                INSERT INTO cart_items (user_id, product_id, color_id, size_id, quantity)
                VALUES (:user_id, :product_id, :color_id, :size_id, :quantity)
            """), {
                'user_id': user_id,
                'product_id': product_id,
                'color_id': color_id,
                'size_id': size_id,
                'quantity': quantity
            })

    # 5. Send them to the cart page to see their item
    return redirect(url_for('cart'))



@app.route('/cart')
def cart():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    with engine.connect() as conn:
        items = conn.execute(text("""
            SELECT 
                c.id, p.title, p.price, cat.name as category_name, 
                v.name as vendor_name, col.name as color, 
                sz.name as size, c.quantity
            FROM cart_items c
            JOIN products p ON c.product_id = p.id
            JOIN categories cat ON p.category_id = cat.id
            JOIN users v ON p.vendor_id = v.id
            LEFT JOIN colors col ON c.color_id = col.id
            LEFT JOIN sizes sz ON c.size_id = sz.id
            WHERE c.user_id = :user_id
        """), {"user_id": user_id}).mappings().all()

    # Calculate the grand total
    grand_total = sum(item['price'] * item['quantity'] for item in items)

    return render_template('cart.html', items=items, grand_total=grand_total)


@app.route('/remove-from-cart/<int:cart_id>', methods=['POST'])
def remove_from_cart(cart_id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    with engine.begin() as conn:
        # We check user_id to make sure people can't delete other people's items
        conn.execute(text("""
            DELETE FROM cart_items 
            WHERE id = :cart_id AND user_id = :user_id
        """), {"cart_id": cart_id, "user_id": user_id})

    return redirect(url_for('cart'))


@app.route('/checkout')
def checkout():
    with engine.connect() as conn:
        cart_items = conn.execute(text("""
            SELECT * FROM cart_items WHERE user_id=:user_id
        """), {"user_id": session['user_id']}).fetchall()

        total = 0
        for item in cart_items:
            product = conn.execute(text("""
                SELECT price, vendor_id FROM products WHERE id=:id
            """), {"id": item.product_id}).fetchone()

            total += product.price * item.quantity

        result = conn.execute(text("""
            INSERT INTO orders (user_id, total_price)
            VALUES (:user_id, :total)
        """), {"user_id": session['user_id'], "total": total})

        order_id = result.lastrowid

        for item in cart_items:
            product = conn.execute(text("""
                SELECT price, vendor_id FROM products WHERE id=:id
            """), {"id": item.product_id}).fetchone()

            conn.execute(text("""
                INSERT INTO order_items
                (order_id, product_id, vendor_id, quantity, price)
                VALUES (:order_id, :product_id, :vendor_id, :quantity, :price)
            """), {
                "order_id": order_id,
                "product_id": item.product_id,
                "vendor_id": product.vendor_id,
                "quantity": item.quantity,
                "price": product.price
            })

        conn.execute(text("""
            DELETE FROM cart_items WHERE user_id=:user_id
        """), {"user_id": session['user_id']})

        conn.commit()

    return redirect('/orders')


    return render_template('orders.html', orders=orders)
@app.route('/add-review', methods=['POST'])
def add_review():
    data = request.form

    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO reviews (user_id, product_id, rating, description)
            VALUES (:user_id, :product_id, :rating, :description)
        """), {
            **data,
            "user_id": session['user_id']
        })
        conn.commit()

    return redirect(f"/product/{data['product_id']}")

@app.route('/complaint', methods=['POST'])
def complaint():
    data = request.form

    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO complaints (user_id, order_item_id, title, description, demand)
            VALUES (:user_id, :order_item_id, :title, :description, :demand)
        """), {
            **data,
            "user_id": session['user_id']
        })
        conn.commit()

    return redirect('/orders')

@app.route('/chat/<int:receiver_id>', methods=['GET', 'POST'])
def chat(receiver_id):
    if request.method == 'POST':
        msg = request.form['message']

        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO chats (sender_id, receiver_id, message)
                VALUES (:sender, :receiver, :message)
            """), {
                "sender": session['user_id'],
                "receiver": receiver_id,
                "message": msg
            })
            conn.commit()

    with engine.connect() as conn:
        messages = conn.execute(text("""
            SELECT * FROM chats
            WHERE (sender_id=:me AND receiver_id=:them)
               OR (sender_id=:them AND receiver_id=:me)
            ORDER BY created_at
        """), {
            "me": session['user_id'],
            "them": receiver_id
        }).fetchall()
    return render_template('chat.html', messages=messages, receiver_id=receiver_id)
# --- HOME ROUTE (INDEX) ---
@app.route('/')
def home():
    # 1. Capture filters from request
    search = request.args.get('search', '')
    category_id = request.args.get('category')
    color_id = request.args.get('color')
    sort = request.args.get('sort')

    # 2. Main Query - MUST include p.vendor_id for the HTML button check to work!
    query_str = """
        SELECT p.id, p.title, p.price, p.vendor_id,
               IFNULL(AVG(r.rating), 0) AS avg_rating,
               (SELECT image_url FROM product_images WHERE product_id = p.id LIMIT 1) as image_url
        FROM products p
        LEFT JOIN reviews r ON p.id = r.product_id
        LEFT JOIN product_colors pc ON p.id = pc.product_id
        WHERE 1=1
    """
    params = {}

    if search:
        query_str += " AND (p.title LIKE :s OR p.description LIKE :s)"
        params['s'] = f"%{search}%"
    if category_id:
        query_str += " AND p.category_id = :cid"
        params['cid'] = category_id
    if color_id:
        query_str += " AND pc.color_id = :color_id"
        params['color_id'] = color_id

    query_str += " GROUP BY p.id"

    # Sorting
    if sort == 'rating_desc': query_str += " ORDER BY avg_rating DESC"
    elif sort == 'price_asc': query_str += " ORDER BY p.price ASC"
    else: query_str += " ORDER BY p.created_at DESC"

    with engine.connect() as conn:
        products = conn.execute(text(query_str), params).mappings().all()
        categories = conn.execute(text("SELECT * FROM categories")).mappings().all()
        colors = conn.execute(text("SELECT * FROM colors")).mappings().all()

    return render_template('home.html', products=products, categories=categories, colors=colors)


@app.route('/delete-product/<int:id>', methods=['POST'])
def delete_product(id):
    if 'user_id' not in session:
        return redirect('/login')

    with engine.connect() as conn:
        product = conn.execute(text("SELECT vendor_id FROM products WHERE id = :id"), {"id": id}).mappings().fetchone()
        
        if not product: return "Not found", 404
        
        # Security: Only Admin or the Vendor who owns the item
        if session.get('role') == 'admin' or session.get('user_id')|int == product['vendor_id']|int:
            with engine.begin() as trans_conn:
                trans_conn.execute(text("DELETE FROM products WHERE id = :id"), {"id": id})
            return redirect(url_for('index'))
        
        return "Unauthorized", 403






@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        return "Unauthorized", 403

    with engine.connect() as conn:
        # Get only vendors that are NOT approved
        pending = conn.execute(text("""
            SELECT id, name, email, username FROM users 
            WHERE role = 'vendor' AND is_approved = 0
        """)).fetchall()
        
    return render_template('admin.html', pending_users=pending)

@app.route('/admin/approve/<int:user_id>', methods=['POST'])
def approve_user(user_id):
    if session.get('role') != 'admin':
        return "Unauthorized", 403

    with engine.connect() as conn:
        conn.execute(text("UPDATE users SET is_approved = 1 WHERE id = :id"), {"id": user_id})
        conn.commit()
        
    return redirect('/admin')

@app.route('/my-account')
def my_account():
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/login')

    with engine.connect() as conn:
        user = conn.execute(text("SELECT * FROM users WHERE id = :id"), {"id": user_id}).mappings().fetchone()
        stats = {}

        if user.role == 'vendor':
            # Vendor Stats
            stats['total_products'] = conn.execute(text("SELECT COUNT(*) FROM products WHERE vendor_id = :id"), {"id": user_id}).scalar()
            stats['total_sold'] = conn.execute(text("SELECT IFNULL(SUM(quantity), 0) FROM order_items WHERE vendor_id = :id"), {"id": user_id}).scalar()
            
            # Incoming Orders for Vendor
            stats['customer_orders'] = conn.execute(text("""
                SELECT oi.*, p.title as product_title, o.status, o.created_at, u.name as customer_name
                FROM order_items oi
                JOIN orders o ON oi.order_id = o.id
                JOIN products p ON oi.product_id = p.id
                JOIN users u ON o.user_id = u.id
                WHERE oi.vendor_id = :id
                ORDER BY o.created_at DESC
            """), {"id": user_id}).mappings().all()
        else:
            # Customer Stats
            stats['total_orders'] = conn.execute(text("SELECT COUNT(*) FROM orders WHERE user_id = :id"), {"id": user_id}).scalar()
            stats['recent_orders'] = conn.execute(text("SELECT * FROM orders WHERE user_id = :id ORDER BY created_at DESC"), {"id": user_id}).mappings().all()

    return render_template('my_account.html', user=user, stats=stats)


# --- VIEW PRODUCT ---
@app.route('/product/<int:id>')
def product_page(id):
    with engine.connect() as conn:
        # Fetch product with AVG rating and Vendor details
        product = conn.execute(text("""
            SELECT p.*, c.name as category_name, v.name as vendor_name,
                   IFNULL(AVG(r.rating), 0) as avg_rating,
                   COUNT(r.id) as review_count
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            LEFT JOIN users v ON p.vendor_id = v.id
            LEFT JOIN reviews r ON p.id = r.product_id
            WHERE p.id = :id
            GROUP BY p.id
        """), {"id": id}).mappings().fetchone()

        if not product: return "Product not found", 404

        # Fetch supporting data
        images = conn.execute(text("SELECT image_url FROM product_images WHERE product_id = :id"), {"id": id}).mappings().all()
        colors = conn.execute(text("SELECT c.id, c.name FROM colors c JOIN product_colors pc ON c.id = pc.color_id WHERE pc.product_id = :id"), {"id": id}).mappings().all()
        sizes = conn.execute(text("SELECT s.id, s.name FROM sizes s JOIN product_sizes ps ON s.id = ps.size_id WHERE ps.product_id = :id"), {"id": id}).mappings().all()
        reviews = conn.execute(text("SELECT r.*, u.name as user_name FROM reviews r JOIN users u ON r.user_id = u.id WHERE product_id = :id ORDER BY created_at DESC"), {"id": id}).mappings().all()

    return render_template('product.html', product=product, images=images, colors=colors, sizes=sizes, reviews=reviews)


# --- ADD PRODUCT ---
@app.route('/add-product', methods=['GET', 'POST'])
def add_product():
    if 'user_id' not in session or session.get('role') not in ['admin', 'vendor']:
        return redirect('/login')

    if request.method == 'POST':
        with engine.begin() as conn:
            # 1. Insert Main Product
            res = conn.execute(text("""
                INSERT INTO products (vendor_id, title, description, price, old_price, discount_start, discount_end, inventory, category_id)
                VALUES (:v_id, :t, :d, :p, :op, :ds, :de, :inv, :cid)
            """), {
                "v_id": session['user_id'], "t": request.form.get('title'), "d": request.form.get('description'),
                "p": request.form.get('price'), "op": request.form.get('old_price') or None,
                "ds": request.form.get('discount_start') or None, "de": request.form.get('discount_end') or None,
                "inv": request.form.get('inventory'), "cid": request.form.get('category_id')
            })
            product_id = res.lastrowid

            # 2. Handle Image
            file = request.files.get('image')
            if file and file.filename != '':
                filename = secure_filename(f"{product_id}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                conn.execute(text("INSERT INTO product_images (product_id, image_url) VALUES (:pid, :url)"), {"pid": product_id, "url": filename})

            # 3. Handle Colors & Sizes (Comma Separated)
            for key, table, link_table, col_name in [('colors', 'colors', 'product_colors', 'color_id'), ('sizes', 'sizes', 'product_sizes', 'size_id')]:
                items = [i.strip() for i in request.form.get(key, '').split(',') if i.strip()]
                for item in items:
                    conn.execute(text(f"INSERT IGNORE INTO {table} (name) VALUES (:n)"), {"n": item})
                    item_id = conn.execute(text(f"SELECT id FROM {table} WHERE name = :n"), {"n": item}).scalar()
                    conn.execute(text(f"INSERT INTO {link_table} (product_id, {col_name}) VALUES (:pid, :iid)"), {"pid": product_id, "iid": item_id})

        return redirect(url_for('product_page', id=product_id))

    with engine.connect() as conn:
        categories = conn.execute(text("SELECT * FROM categories")).mappings().all()
    return render_template('add_product.html', categories=categories)


# --- EDIT PRODUCT ---
@app.route('/edit-product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    if 'user_id' not in session or session.get('role') not in ['admin', 'vendor']:
        return redirect('/login')

    with engine.connect() as conn:
        # 1. Fetch Product
        product = conn.execute(text("SELECT * FROM products WHERE id = :id"), {"id": id}).mappings().fetchone()
        
        if not product:
            return "Product not found", 404
        if session['role'] == 'vendor' and product['vendor_id'] != session['user_id']:
            return "Unauthorized", 403

        if request.method == 'POST':
            with engine.begin() as edit_conn:
                # 2. Update Main Product Table
                edit_conn.execute(text("""
                    UPDATE products 
                    SET title=:t, description=:d, price=:p, old_price=:op,
                        discount_start=:ds, discount_end=:de, category_id=:cid, inventory=:inv 
                    WHERE id=:id
                """), {
                    "t": request.form.get('title'), "d": request.form.get('description'),
                    "p": request.form.get('price'), "op": request.form.get('old_price') or None,
                    "ds": request.form.get('discount_start') or None, "de": request.form.get('discount_end') or None,
                    "cid": request.form.get('category_id'), "inv": request.form.get('inventory'), "id": id
                })

                # 3. Handle Colors & Sizes (Clear and Re-sync)
                for key, table, link_table, col_name in [
                    ('colors', 'colors', 'product_colors', 'color_id'),
                    ('sizes', 'sizes', 'product_sizes', 'size_id')
                ]:
                    edit_conn.execute(text(f"DELETE FROM {link_table} WHERE product_id = :id"), {"id": id})
                    items = [i.strip() for i in request.form.get(key, '').split(',') if i.strip()]
                    for item in items:
                        edit_conn.execute(text(f"INSERT IGNORE INTO {table} (name) VALUES (:n)"), {"n": item})
                        item_id = edit_conn.execute(text(f"SELECT id FROM {table} WHERE name = :n"), {"n": item}).scalar()
                        edit_conn.execute(text(f"INSERT INTO {link_table} (product_id, {col_name}) VALUES (:pid, :iid)"), {"pid": id, "iid": item_id})

            return redirect(url_for('product_page', id=id))

        # GET: Prepare form data
        categories = conn.execute(text("SELECT * FROM categories")).mappings().all()
        
        # FIXED: Corrected Aliases (pc for colors, ps for sizes)
        curr_colors = conn.execute(text("""
            SELECT GROUP_CONCAT(c.name SEPARATOR ', ') FROM colors c 
            JOIN product_colors pc ON c.id = pc.color_id WHERE pc.product_id = :id
        """), {"id": id}).scalar() or ""

        curr_sizes = conn.execute(text("""
            SELECT GROUP_CONCAT(s.name SEPARATOR ', ') FROM sizes s 
            JOIN product_sizes ps ON s.id = ps.size_id WHERE ps.product_id = :id
        """), {"id": id}).scalar() or ""

    return render_template('edit_product.html', product=product, categories=categories, colors=curr_colors, sizes=curr_sizes)

@app.route('/place-order', methods=['POST'])
def place_order():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    with engine.begin() as conn:
        # 1. Get current cart items
        cart_items = conn.execute(text("""
            SELECT c.*, p.price, p.vendor_id 
            FROM cart_items c 
            JOIN products p ON c.product_id = p.id 
            WHERE c.user_id = :uid
        """), {"uid": user_id}).mappings().all()

        if not cart_items:
            return redirect(url_for('cart'))

        total_price = sum(item['price'] * item['quantity'] for item in cart_items)

        # 2. Insert into orders table
        result = conn.execute(text("""
            INSERT INTO orders (user_id, total_price, status) 
            VALUES (:uid, :total, 'pending')
        """), {"uid": user_id, "total": total_price})
        
        order_id = result.lastrowid

        # 3. Move items to order_items table
        for item in cart_items:
            conn.execute(text("""
                INSERT INTO order_items (order_id, product_id, vendor_id, color_id, size_id, quantity, price)
                VALUES (:oid, :pid, :vid, :cid, :sid, :qty, :price)
            """), {
                "oid": order_id, "pid": item['product_id'], "vid": item['vendor_id'],
                "cid": item['color_id'], "sid": item['size_id'], 
                "qty": item['quantity'], "price": item['price']
            })

        # 4. Clear the cart
        conn.execute(text("DELETE FROM cart_items WHERE user_id = :uid"), {"uid": user_id})

    return redirect(url_for('orders'))

@app.route('/orders')
def orders():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    with engine.connect() as conn:
        # Fetch all orders for this user
        user_orders = conn.execute(text("""
            SELECT id, total_price, status, created_at 
            FROM orders 
            WHERE user_id = :uid 
            ORDER BY created_at DESC
        """), {"uid": user_id}).mappings().all()

    return render_template('orders.html', orders=user_orders)

@app.route('/order/<int:order_id>')
def order_details(order_id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    with engine.connect() as conn:
        # 1. Fetch the main order info
        order = conn.execute(text("""
            SELECT * FROM orders WHERE id = :oid AND user_id = :uid
        """), {"oid": order_id, "uid": user_id}).mappings().fetchone()

        if not order:
            return "Order not found or unauthorized", 404

        # 2. Fetch the specific items in that order
        items = conn.execute(text("""
            SELECT 
                oi.quantity, oi.price, p.title, 
                col.name as color, sz.name as size
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            LEFT JOIN colors col ON oi.color_id = col.id
            LEFT JOIN sizes sz ON oi.size_id = sz.id
            WHERE oi.order_id = :oid
        """), {"oid": order_id}).mappings().all()

    return render_template('order_details.html', order=order, items=items)
@app.route('/submit-review/<int:product_id>', methods=['POST'])
def submit_review(product_id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    rating = request.form.get('rating')
    description = request.form.get('description')

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO reviews (user_id, product_id, rating, description)
            VALUES (:uid, :pid, :rating, :desc)
        """), {
            "uid": user_id,
            "pid": product_id,
            "rating": rating,
            "desc": description
        })

    return redirect(url_for('product_page', id=product_id))
# CUSTOMER: Submit a complaint
@app.route('/complaint/new/<int:order_item_id>', methods=['GET', 'POST'])
def file_complaint(order_item_id):
    if 'user_id' not in session: return redirect('/login')

    if request.method == 'POST':
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO complaints (user_id, order_item_id, title, description, demand, status)
                VALUES (:u_id, :oi_id, :t, :d, :dem, 'pending')
            """), {
                "u_id": session['user_id'], 
                "oi_id": order_item_id, 
                "t": request.form['title'], 
                "d": request.form['description'], 
                "dem": request.form['demand']
            })
            conn.commit()
        return redirect('/my-complaints')

    return render_template('file_complaint.html', order_item_id=order_item_id)

# VENDOR: View complaints for their products
@app.route('/vendor/complaints')
def vendor_complaints():
    if session.get('role') != 'vendor': return "Access Denied"

    with engine.connect() as conn:
        query = text("""
            SELECT c.*, p.title as product_name, u.name as customer_name
            FROM complaints c
            JOIN order_items oi ON c.order_item_id = oi.id
            JOIN products p ON oi.product_id = p.id
            JOIN users u ON c.user_id = u.id
            WHERE oi.vendor_id = :vendor_id
        """)
        results = conn.execute(query, {"vendor_id": session['user_id']}).fetchall()
    return render_template('vendor_complaints.html', complaints=results)

# BOTH: Update status (Vendor or Admin)
@app.route('/complaint/update/<int:complaint_id>', methods=['POST'])
def update_complaint_status(complaint_id):
    new_status = request.form['status']
    with engine.connect() as conn:
        conn.execute(text("UPDATE complaints SET status = :status WHERE id = :id"),
                    {"status": new_status, "id": complaint_id})
        conn.commit()
    return redirect(request.referrer)

@app.route('/my-complaints')
def my_complaints():
    if 'user_id' not in session: return redirect('/login')
    with engine.connect() as conn:
        query = text("""
            SELECT c.*, p.title as product_name 
            FROM complaints c
            JOIN order_items oi ON c.order_item_id = oi.id
            JOIN products p ON oi.product_id = p.id
            WHERE c.user_id = :u_id
            ORDER BY c.created_at DESC
        """)
        results = conn.execute(query, {"u_id": session['user_id']}).fetchall()
    return render_template('my_complaints.html', complaints=results)


@app.route('/ship-order/<int:order_id>', methods=['POST'])
def ship_order(order_id):
    # 1. Security check: make sure user is logged in and is a vendor
    if 'user_id' not in session or session.get('role') != 'vendor':
        return redirect('/login')

    with engine.begin() as conn:
        # 2. Update the status of the order to 'shipped'
        conn.execute(text("""
            UPDATE orders 
            SET status = 'shipped' 
            WHERE id = :oid
        """), {"oid": order_id})
        
    # 3. Redirect back to the account page to see the updated status
    return redirect(url_for('my_account'))



if __name__ == '__main__':  # When this file is run...
    # ... start the app in debug mode. In debug mode,
    # server is automatically restarted when you make changes to the codex
    app.run(debug=True)