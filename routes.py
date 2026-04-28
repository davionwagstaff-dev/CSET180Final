from flask import Flask, render_template, request, redirect, session, url_for
from sqlalchemy import create_engine, text

app = Flask(__name__)
app.secret_key = "secret123"

engine = create_engine("mysql+pymysql://root:Yohan969$$@localhost/ecommerce")


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form

        with engine.connect() as conn:
            # Check duplicate email
            existing = conn.execute(text("""
                SELECT * FROM users WHERE email = :email
            """), {"email": data['email']}).fetchone()

            if existing:
                return "Email already exists"

            conn.execute(text("""
                INSERT INTO users (name, email, username, password, role)
                VALUES (:name, :email, :username, :password, :role)
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
                WHERE (email = :login OR username = :login)
                AND password = :password
            """), {
                "login": data['login'],
                "password": data['password']
            }).fetchone()

            if user:
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
        product = conn.execute(text("""
            SELECT * FROM products WHERE id = :id
        """), {"id": id}).fetchone()

        reviews = conn.execute(text("""
            SELECT r.*, u.name 
            FROM reviews r
            JOIN users u ON r.user_id = u.id
            WHERE product_id = :id
        """), {"id": id}).fetchall()

    return render_template('product.html', product=product, reviews=reviews)


@app.route('/edit-product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    if request.method == 'POST':
        data = request.form

        with engine.connect() as conn:
            conn.execute(text("""
                UPDATE products
                SET title=:title, description=:description, price=:price, inventory=:inventory
                WHERE id=:id
            """), {**data, "id": id})
            conn.commit()

        return redirect('/')

    return render_template('edit_product.html')

@app.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    data = request.form

    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO cart_items (user_id, product_id, color_id, size_id, quantity)
            VALUES (:user_id, :product_id, :color_id, :size_id, :quantity)
        """), {
            **data,
            "user_id": session['user_id']
        })
        conn.commit()

    return redirect('/cart')

@app.route('/cart')
def cart():
    with engine.connect() as conn:
        items = conn.execute(text("""
            SELECT c.*, p.title, p.price
            FROM cart_items c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = :user_id
        """), {"user_id": session['user_id']}).fetchall()

    return render_template('cart.html', items=items)

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

@app.route('/orders')
def orders():
    with engine.connect() as conn:
        orders = conn.execute(text("""
            SELECT * FROM orders WHERE user_id=:user_id
        """), {"user_id": session['user_id']}).fetchall()

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
            SELECT * FROM products WHERE id=:id
        """), {"id": id}).fetchone()

        # Only admin OR the vendor who owns it
        if session.get('role') != 'admin' and product.vendor_id != session['user_id']:
            return "Unauthorized"

        conn.execute(text("DELETE FROM products WHERE id=:id"), {"id": id})
        conn.commit()

    return redirect('/')
@app.route('/add-product', methods=['GET', 'POST'])
def add_product():
    if session.get('role') not in ['vendor', 'admin']:
        return "Unauthorized"

    if request.method == 'POST':
        data = request.form
        image_name = data.get('image')  # just filename

        with engine.connect() as conn:
            result = conn.execute(text("""
                INSERT INTO products 
                (vendor_id, title, description, price, inventory, category_id)
                VALUES (:vendor_id, :title, :description, :price, :inventory, :category_id)
            """), {
                **data,
                "vendor_id": session['user_id']
            })

            product_id = result.lastrowid

            if image_name:
                conn.execute(text("""
                    INSERT INTO product_images (product_id, image_url)
                    VALUES (:product_id, :image_url)
                """), {
                    "product_id": product_id,
                    "image_url": image_name
                })

            conn.commit()

        return redirect('/')

    return render_template('add_product.html')
@app.route('/')
def home():
    with engine.connect() as conn:
        products = conn.execute(text("""
            SELECT p.*, pi.image_url
            FROM products p
            LEFT JOIN product_images pi ON p.id = pi.product_id
        """)).fetchall()

    return render_template('home.html', products=products)
if __name__ == '__main__':  # When this file is run...
    # ... start the app in debug mode. In debug mode,
    # server is automatically restarted when you make changes to the code
    app.run(debug=True)