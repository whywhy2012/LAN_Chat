from flask import Flask, render_template, request, redirect, url_for, flash
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 用户数据
users = {}
chat_history = []
# 存储在线用户的sid (session id)
online_users = {}

# 用户类
class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(username):
    if username in users:
        return User(username)
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in users and check_password_hash(users[username], password):
            user = User(username)
            login_user(user)
            return redirect(url_for('index'))
        flash('用户名或密码错误')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in users:
            flash('用户名已存在')
            return redirect(url_for('register'))
        
        users[username] = generate_password_hash(password)
        user = User(username)
        login_user(user)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', 
                         chat_history=chat_history, 
                         online_users=list(online_users.keys()))

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        online_users[current_user.id] = request.sid
        print(f"User connected: {current_user.id}")
        print(f"Current online users: {list(online_users.keys())}")
        print(f"Emitting update_users event with users: {list(online_users.keys())}")
        emit('update_users', list(online_users.keys()), broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        if current_user.id in online_users:
            online_users.pop(current_user.id)
            print(f"User disconnected: {current_user.id}")
            print(f"Current online users: {list(online_users.keys())}")
            print(f"Emitting update_users event with users: {list(online_users.keys())}")
            emit('update_users', list(online_users.keys()), broadcast=True)

@socketio.on('send_message')
def handle_message(message):
    if current_user.is_authenticated:
        message = f"{current_user.id}: {message}"
        chat_history.append(message)
        print(f"Broadcasting message: {message}")
        emit('new_message', message, broadcast=True)

# WebRTC信令服务器
@socketio.on('offer')
def handle_offer(data):
    if current_user.is_authenticated and data['target'] in online_users:
        emit('offer', {
            'offer': data['offer'],
            'sender': current_user.id
        }, to=online_users[data['target']])

@socketio.on('answer')
def handle_answer(data):
    if current_user.is_authenticated and data['target'] in online_users:
        emit('answer', {
            'answer': data['answer'],
            'sender': current_user.id
        }, to=online_users[data['target']])

@socketio.on('ice-candidate')
def handle_ice_candidate(data):
    if current_user.is_authenticated and data['target'] in online_users:
        emit('ice-candidate', {
            'candidate': data['candidate'],
            'sender': current_user.id
        }, to=online_users[data['target']])

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=80) 