from flask import Flask, render_template, request, redirect, url_for, flash
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
import time
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 用户数据文件路径
USERS_FILE = 'users.json'

# 加载用户数据
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

# 保存用户数据
def save_users(users_data):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users_data, f, ensure_ascii=False, indent=4)

# 初始化数据
users = load_users()
# 聊天历史格式: [{'id': 'msg_id', 'sender': 'username', 'content': 'message', 'timestamp': time.time()}]
chat_history = []
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
        
        # 检查用户是否已在线
        if username in online_users:
            flash('该账号已在其他设备登录')
            return redirect(url_for('login'))
        
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
        save_users(users)  # 保存用户数据到文件
        
        user = User(username)
        login_user(user)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    if current_user.is_authenticated and current_user.id in online_users:
        # 确保用户从在线列表中移除
        online_users.pop(current_user.id)
        emit('update_users', list(online_users.keys()), broadcast=True, namespace='/')
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    # 如果用户已在其他设备登录，强制登出
    if current_user.id in online_users and online_users[current_user.id] != request.sid:
        logout_user()
        flash('该账号已在其他设备登录')
        return redirect(url_for('login'))
    
    # 转换消息格式用于显示
    formatted_history = []
    for msg in chat_history:
        if msg.get('is_recalled', False):
            formatted_history.append({'id': msg['id'], 'content': '该消息已被撤回', 'sender': msg['sender'], 'is_recalled': True})
        else:
            can_recall = time.time() - msg['timestamp'] <= 120 and msg['sender'] == current_user.id
            formatted_history.append({
                'id': msg['id'],
                'content': msg['content'],
                'sender': msg['sender'],
                'can_recall': can_recall
            })
    
    return render_template('index.html', 
                         chat_history=formatted_history, 
                         online_users=list(online_users.keys()))

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        # 检查用户是否已在其他设备登录
        if current_user.id in online_users and online_users[current_user.id] != request.sid:
            # 返回错误状态，阻止连接
            return False
        
        online_users[current_user.id] = request.sid
        print(f"User connected: {current_user.id}")
        print(f"Current online users: {list(online_users.keys())}")
        emit('update_users', list(online_users.keys()), broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        if current_user.id in online_users:
            online_users.pop(current_user.id)
            print(f"User disconnected: {current_user.id}")
            print(f"Current online users: {list(online_users.keys())}")
            emit('update_users', list(online_users.keys()), broadcast=True)

@socketio.on('send_message')
def handle_message(message):
    if current_user.is_authenticated:
        msg_id = str(uuid.uuid4())
        msg_data = {
            'id': msg_id,
            'sender': current_user.id,
            'content': message,
            'timestamp': time.time()
        }
        chat_history.append(msg_data)
        
        # 发送消息时包含消息ID和是否可撤回的信息
        emit('new_message', {
            'id': msg_id,
            'content': message,
            'sender': current_user.id,
            'can_recall': True
        }, broadcast=True)

@socketio.on('recall_message')
def handle_recall(data):
    if current_user.is_authenticated:
        msg_id = data.get('message_id')
        for msg in chat_history:
            if msg['id'] == msg_id and msg['sender'] == current_user.id:
                # 检查是否在2分钟内
                if time.time() - msg['timestamp'] <= 120:
                    msg['is_recalled'] = True
                    # 广播消息已被撤回
                    emit('message_recalled', {
                        'message_id': msg_id
                    }, broadcast=True)
                    return
                else:
                    emit('recall_error', {'error': '消息发送超过2分钟，无法撤回'}, room=request.sid)
                    return
        
        emit('recall_error', {'error': '消息不存在或无权操作'}, room=request.sid)

if __name__ == '__main__':
    # 确保用户数据文件存在
    if not os.path.exists(USERS_FILE):
        save_users({})
        
    socketio.run(app, host='0.0.0.0', port=80) 