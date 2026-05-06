import os
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, session, url_for
from sqlalchemy import create_engine, text

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


@app.route('/product/<int:id>')
def product_page(id):
    with engine.connect() as conn:
        # 1. Fetch Product with Mappings
        product = conn.execute(text("""
            SELECT p.*, c.name as category_name, v.name as vendor_name
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            LEFT JOIN users v ON p.vendor_id = v.id
            WHERE p.id = :id
        """), {"id": id}).mappings().fetchone()

        if not product:
            return "Product not found", 404

        # 2. Fetch images (mappings so we can use img['image_url'])
        images = conn.execute(text("""
            SELECT image_url FROM product_images WHERE product_id = :id
        """), {"id": id}).mappings().fetchall()

        # 3. Fetch Colors & Sizes
        colors = conn.execute(text("""
            SELECT c.id, c.name FROM colors c 
            JOIN product_colors pc ON c.id = pc.color_id 
            WHERE pc.product_id = :id
        """), {"id": id}).mappings().fetchall()

        sizes = conn.execute(text("""
            SELECT s.id, s.name FROM sizes s 
            JOIN product_sizes ps ON s.id = ps.size_id 
            WHERE ps.product_id = :id
        """), {"id": id}).mappings().fetchall()

        # 4. Fetch Reviews
        reviews = conn.execute(text("""
            SELECT r.*, u.name as user_name FROM reviews r 
            JOIN users u ON r.user_id = u.id 
            WHERE product_id = :id
        """), {"id": id}).mappings().fetchall()

    return render_template('product.html', product=product, images=images, colors=colors, sizes=sizes, reviews=reviews)



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
            # 2. Update Main Product Table
            conn.execute(text("""
                UPDATE products 
                SET title=:t, description=:d, price=:p, category_id=:cid, inventory=:inv 
                WHERE id=:id
            """), {
                "t": request.form.get('title'), "d": request.form.get('description'),
                "p": request.form.get('price'), "cid": request.form.get('category_id'),
                "inv": request.form.get('inventory'), "id": id
            })

            # 3. Handle Colors (Clears old links, adds new ones)
            raw_colors = request.form.get('new_colors', '')
            conn.execute(text("DELETE FROM product_colors WHERE product_id = :id"), {"id": id})
            if raw_colors:
                color_list = [c.strip() for c in raw_colors.split(',') if c.strip()]
                for name in color_list:
                    conn.execute(text("INSERT IGNORE INTO colors (name) VALUES (:n)"), {"n": name})
                    c_id = conn.execute(text("SELECT id FROM colors WHERE name = :n"), {"n": name}).scalar()
                    conn.execute(text("INSERT INTO product_colors (product_id, color_id) VALUES (:pid, :cid)"), {"pid": id, "cid": c_id})

            # 4. Handle Sizes
            raw_sizes = request.form.get('new_sizes', '')
            conn.execute(text("DELETE FROM product_sizes WHERE product_id = :id"), {"id": id})
            if raw_sizes:
                size_list = [s.strip() for s in raw_sizes.split(',') if s.strip()]
                for name in size_list:
                    conn.execute(text("INSERT IGNORE INTO sizes (name) VALUES (:n)"), {"n": name})
                    s_id = conn.execute(text("SELECT id FROM sizes WHERE name = :n"), {"n": name}).scalar()
                    conn.execute(text("INSERT INTO product_sizes (product_id, size_id) VALUES (:pid, :sid)"), {"pid": id, "sid": s_id})

            conn.commit()
            return redirect(url_for('product_page', id=id))

        # GET: Prepare form data
        categories = conn.execute(text("SELECT id, name FROM categories")).mappings().all()
        
        # Get existing colors/sizes as strings for the input boxes
        curr_colors = conn.execute(text("""
            SELECT GROUP_CONCAT(c.name SEPARATOR ', ') FROM colors c 
            JOIN product_colors pc ON c.id = pc.color_id WHERE pc.product_id = :id
        """), {"id": id}).scalar() or ""

        curr_sizes = conn.execute(text("""
            SELECT GROUP_CONCAT(s.name SEPARATOR ', ') FROM sizes s 
            JOIN product_sizes ps ON s.id = ps.size_id WHERE ps.product_id = :id
        """), {"id": id}).scalar() or ""

    return render_template('edit_product.html', product=product, categories=categories, curr_colors=curr_colors, curr_sizes=curr_sizes)






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
@app.route('/delete-product/<int:id>', methods=['POST'])
def delete_product(id):
    if 'user_id' not in session:
        return redirect('/login')

    with engine.connect() as conn:
        product = conn.execute(text("""
            SELECT vendor_id FROM products WHERE id=:id
        """), {"id": id}).fetchone()

        if not product:
            return "Product not found"

        # Admin OR owner vendor
        if session.get('role') != 'admin' and product.vendor_id != session['user_id']:
            return "Unauthorized"

        conn.execute(text("DELETE FROM products WHERE id=:id"), {"id": id})
        conn.commit()

    return redirect('/')
@app.route('/')
def home():
    # Get filter values
    search = request.args.get('search', '')
    cat_id = request.args.get('category', '')
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')

    # FIX: We use MIN(pi.image_url) so MySQL picks one image per product
    query = """
        SELECT 
            p.id, 
            p.title, 
            p.price, 
            p.vendor_id, 
            MIN(pi.image_url) as image_url
        FROM products p
        LEFT JOIN product_images pi ON p.id = pi.product_id
        WHERE 1=1
    """
    params = {}

    if search:
        query += " AND (p.title LIKE :search OR p.description LIKE :search)"
        params['search'] = f"%{search}%"
    
    if cat_id:
        query += " AND p.category_id = :cat_id"
        params['cat_id'] = cat_id
        
    if min_price:
        query += " AND p.price >= :min_price"
        params['min_price'] = min_price
        
    if max_price:
        query += " AND p.price <= :max_price"
        params['max_price'] = max_price

    query += " GROUP BY p.id"

    with engine.connect() as conn:
        products = conn.execute(text(query), params).mappings().all()
        categories = conn.execute(text("SELECT * FROM categories")).mappings().all()

    return render_template('home.html', products=products, categories=categories)



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
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    role = session.get('role')

    with engine.connect() as conn:
        # 1. Fetch User Info
        user_query = text("SELECT name, email, username, role, created_at FROM users WHERE id = :uid")
        user_info = conn.execute(user_query, {"uid": user_id}).mappings().fetchone()

        stats_data = {}

        if role == 'vendor':
            # Get vendor stats
            prod_query = text("SELECT COUNT(*) as count FROM products WHERE vendor_id = :uid")
            stats_data['total_products'] = conn.execute(prod_query, {"uid": user_id}).scalar() or 0
            
            sold_query = text("SELECT SUM(quantity) as sold FROM order_items WHERE vendor_id = :uid")
            stats_data['total_sold'] = conn.execute(sold_query, {"uid": user_id}).scalar() or 0
        
        else:
            # Get customer stats (order count and recent orders)
            count_query = text("SELECT COUNT(*) FROM orders WHERE user_id = :uid")
            stats_data['total_orders'] = conn.execute(count_query, {"uid": user_id}).scalar() or 0
            
            orders_query = text("""
                SELECT id, total_price, status, created_at 
                FROM orders WHERE user_id = :uid 
                ORDER BY created_at DESC LIMIT 5
            """)
            stats_data['recent_orders'] = conn.execute(orders_query, {"uid": user_id}).mappings().all()

    # Pass 'stats_data' AS 'stats' to the template
    return render_template('my_account.html', user=user_info, stats=stats_data)

@app.route('/add-product', methods=['GET', 'POST'])
def add_product():
    if 'user_id' not in session or session.get('role') not in ['admin', 'vendor']:
        return redirect('/login')

    with engine.connect() as conn:
        if request.method == 'POST':
            # 1. Vendor Logic
            vendor_id = request.form.get('vendor_id') if session.get('role') == 'admin' else session['user_id']
            
            # 2. File Handling
            file = request.files.get('product_image')
            filename = 'default.jpg'
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            # 3. Insert Main Product
            result = conn.execute(text("""
                INSERT INTO products (vendor_id, title, description, price, category_id, inventory)
                VALUES (:vid, :t, :d, :p, :cid, :inv)
            """), {
                "vid": vendor_id, 
                "t": request.form.get('title'), 
                "d": request.form.get('description'),
                "p": request.form.get('price'), 
                "cid": request.form.get('category_id'), 
                "inv": request.form.get('inventory')
            })
            new_id = result.lastrowid
            
            # 4. Link Image
            conn.execute(text("INSERT INTO product_images (product_id, image_url) VALUES (:pid, :url)"),
                         {"pid": new_id, "url": filename})

            # 5. Process Colors (e.g., "Red, Blue")
            raw_colors = request.form.get('new_colors', '')
            if raw_colors:
                color_list = [c.strip() for c in raw_colors.split(',') if c.strip()]
                for color_name in color_list:
                    # Insert if not exists (Requires UNIQUE constraint on colors.name)
                    conn.execute(text("INSERT IGNORE INTO colors (name) VALUES (:n)"), {"n": color_name})
                    # Get ID
                    c_id = conn.execute(text("SELECT id FROM colors WHERE name = :n"), {"n": color_name}).scalar()
                    # Link
                    conn.execute(text("INSERT IGNORE INTO product_colors (product_id, color_id) VALUES (:pid, :cid)"),
                                 {"pid": new_id, "cid": c_id})

            # 6. Process Sizes
            raw_sizes = request.form.get('new_sizes', '')
            if raw_sizes:
                size_list = [s.strip() for s in raw_sizes.split(',') if s.strip()]
                for size_name in size_list:
                    conn.execute(text("INSERT IGNORE INTO sizes (name) VALUES (:n)"), {"n": size_name})
                    s_id = conn.execute(text("SELECT id FROM sizes WHERE name = :n"), {"n": size_name}).scalar()
                    conn.execute(text("INSERT IGNORE INTO product_sizes (product_id, size_id) VALUES (:pid, :sid)"),
                                 {"pid": new_id, "sid": s_id})

            conn.commit()
            return redirect('/')

        # GET: Fetch form data
        categories = conn.execute(text("SELECT id, name FROM categories")).mappings().all()
        vendors = []
        if session.get('role') == 'admin':
            vendors = conn.execute(text("SELECT id, name FROM users WHERE role = 'vendor'")).mappings().all()

    return render_template('add_product.html', categories=categories, vendors=vendors)
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


if __name__ == '__main__':  # When this file is run...
    # ... start the app in debug mode. In debug mode,
    # server is automatically restarted when you make changes to the code
    app.run(debug=True)