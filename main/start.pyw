# remote_control_server.py
from flask import Flask, render_template_string, request, jsonify
import pyautogui
import socket
import threading
import webbrowser
import qrcode
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk
import time
import os
import sys
from datetime import datetime
import random
pyautogui.FAILSAFE = False

app = Flask(__name__)
letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
PASSWORD = ''.join(random.choices(letters, k=6))
tk_root = None

# ============ 连接管理 ============
using = False                 # 是否被占用
current_client = None         # 当前客户端IP
client_name = None            # 客户端名称
connect_time = None           # 连接时间
last_heartbeat = None         # 最后心跳时间
HEARTBEAT_TIMEOUT = 5        # 心跳超时（秒）
HEARTBEAT_CHECK_INTERVAL = 5  # 检查间隔（秒）
lock = threading.Lock()

# ============ 心跳检查线程 ============


def heartbeat_checker():
    """后台线程：定期检查心跳，超时自动释放"""
    global using, current_client, client_name, connect_time, last_heartbeat

    while True:
        time.sleep(HEARTBEAT_CHECK_INTERVAL)
        with lock:
            if using and last_heartbeat:
                elapsed = time.time() - last_heartbeat
                if elapsed > HEARTBEAT_TIMEOUT:
                    old_client = current_client
                    old_name = client_name
                    # 释放连接
                    using = False
                    current_client = None
                    client_name = None
                    connect_time = None
                    last_heartbeat = None
                    print(
                        f"⏰ 心跳超时 ({elapsed:.0f}s)，释放连接: {old_client} ({old_name})")


# 启动心跳检查线程
heartbeat_thread = threading.Thread(target=heartbeat_checker, daemon=True)
heartbeat_thread.start()

# ============ 关闭TK窗口 ============


def destroy_tk():
    global tk_root
    time.sleep(1)
    try:
        if tk_root:
            tk_root.destroy()
            tk_root = None
    except:
        pass

# ============ Flask路由 ============


@app.route('/')
def index():
    try:
        threading.Thread(target=destroy_tk).start()
    except:
        pass
    return render_template_string(HTML_PAGE)


@app.route('/api/control', methods=['POST'])
def control():
    global using, current_client, client_name, connect_time, last_heartbeat

    data = request.json
    client_ip = request.remote_addr

    # 密码校验
    if data.get('password') != PASSWORD:
        return jsonify({'status': 'error', 'msg': '密码错误'}), 401

    action = data.get('action')

    # ===== 连接请求 =====
    if action == 'connect':
        with lock:
            # 如果已被占用，拒绝
            if using:
                return jsonify({
                    'status': 'error',
                    'msg': f'❌ 已被 {client_name or current_client} 占用\n连接时间: {connect_time or "未知"}'
                }), 403

            # 占用连接
            using = True
            current_client = client_ip
            client_name = data.get('name', '未知设备')
            connect_time = datetime.now().strftime('%H:%M:%S')
            last_heartbeat = time.time()
            print(f"📱 {client_ip} ({client_name}) 已连接 [{connect_time}]")
            return jsonify({'status': 'ok', 'msg': '连接成功'})

    # ===== 心跳 =====
    if action == 'heartbeat':
        with lock:
            if not using:
                # 如果连接已释放，让前端重新连接
                return jsonify({'status': 'error', 'msg': '连接已断开，请重新连接'}), 401
            if current_client != client_ip:
                return jsonify({'status': 'error', 'msg': 'IP不匹配'}), 403
            last_heartbeat = time.time()
            return jsonify({'status': 'ok'})

    # ===== 主动断开 =====
    if action == 'disconnect':
        with lock:
            if using and current_client == client_ip:
                old_name = client_name
                using = False
                current_client = None
                client_name = None
                connect_time = None
                last_heartbeat = None
                print(f"📱 {client_ip} ({old_name}) 主动断开")
                return jsonify({'status': 'ok'})
            return jsonify({'status': 'error', 'msg': '未连接或无权断开'}), 403

    # ===== 强制断开（管理员功能） =====
    if action == 'force_disconnect':
        if data.get('admin_key') == 'admin123':
            with lock:
                if using:
                    old_client = current_client
                    old_name = client_name
                    using = False
                    current_client = None
                    client_name = None
                    connect_time = None
                    last_heartbeat = None
                    print(f"🔐 管理员强制断开: {old_client} ({old_name})")
                    return jsonify({'status': 'ok', 'msg': f'已断开 {old_name}'})
                return jsonify({'status': 'ok', 'msg': '当前无连接'})
        return jsonify({'status': 'error', 'msg': '管理员密钥错误'}), 403

    # ===== 获取状态 =====
    if action == 'status':
        with lock:
            if using:
                return jsonify({
                    'status': 'ok',
                    'using': True,
                    'client': current_client,
                    'name': client_name,
                    'connect_time': connect_time,
                    'heartbeat_age': time.time() - last_heartbeat if last_heartbeat else 0
                })
            return jsonify({'status': 'ok', 'using': False})

    # ===== 执行控制动作 =====
    # 检查是否被占用（非当前客户端拒绝）
    with lock:
        if not using:
            return jsonify({'status': 'error', 'msg': '连接已断开，请重新连接'}), 401
        if current_client != client_ip:
            return jsonify({'status': 'error', 'msg': f'当前控制者: {client_name or current_client}'}), 403
        # 更新心跳
        last_heartbeat = time.time()

    screen_w, screen_h = pyautogui.size()

    try:
        if action == 'move_relative':
            dx = data.get('dx', 0)
            dy = data.get('dy', 0)
            x, y = pyautogui.position()
            new_x = max(0, min(x + dx, screen_w - 1))
            new_y = max(0, min(y + dy, screen_h - 1))
            pyautogui.moveTo(new_x, new_y)

        elif action == 'drag':
            dx = data.get('dx', 0)
            dy = data.get('dy', 0)
            x, y = pyautogui.position()
            new_x = max(0, min(x + dx, screen_w - 1))
            new_y = max(0, min(y + dy, screen_h - 1))
            pyautogui.dragTo(new_x, new_y, button='left')

        elif action == 'click':
            pyautogui.click(button=data.get('button', 'left'))
        elif action == 'dclick':
            pyautogui.doubleClick()
        elif action == 'right_click':
            pyautogui.rightClick()
        elif action == 'scroll':
            pyautogui.scroll(data.get('amount', 0))
        elif action == 'key':
            pyautogui.press(data.get('key', ''))
        elif action == 'type':
            pyautogui.typewrite(data.get('text', ''))
        elif action == 'key_combination':
            pyautogui.hotkey(*data.get('keys', []))
        elif action == 'multi_keys':
            keys = data.get('keys', [])
            if keys:
                for key in keys:
                    pyautogui.keyDown(key)
                for key in reversed(keys):
                    pyautogui.keyUp(key)
        elif action == 'key_down':
            pyautogui.keyDown(data.get('key', ''))
        elif action == 'key_up':
            pyautogui.keyUp(data.get('key', ''))
        elif action == 'multi_touch':
            gesture = data.get('gesture', '')
            if gesture == 'pinch_in':
                pyautogui.hotkey('ctrl', '-')
            elif gesture == 'pinch_out':
                pyautogui.hotkey('ctrl', '=')
            elif gesture == 'three_finger_swipe_up':
                pyautogui.hotkey('win', 'tab')
            elif gesture == 'three_finger_swipe_down':
                pyautogui.hotkey('win', 'd')

    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500

    return jsonify({'status': 'ok'})

# ============ 工具函数 ============


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def show_qr_window():
    """显示二维码窗口"""
    global tk_root

    ip = get_local_ip()
    url = f"http://{ip}?pwd={PASSWORD}"

    tk_root = tk.Tk()
    tk_root.title("🖥️ 远程键鼠")
    tk_root.geometry("800x550")  # 宽度800
    tk_root.resizable(False, False)
    tk_root.configure(bg='#0d1117')

    tk_root.attributes('-topmost', True)
    tk_root.lift()

    main_frame = tk.Frame(tk_root, bg='#0d1117')
    main_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)

    title = tk.Label(main_frame, text="🖥️ 远程键鼠",
                     font=('Microsoft YaHei', 22, 'bold'),
                     fg='#58a6ff', bg='#0d1117')
    title.pack(pady=(0, 5))

    sub_title = tk.Label(main_frame, text="手机扫码或浏览器访问",
                         font=('Microsoft YaHei', 12),
                         fg='#8b949e', bg='#0d1117')
    sub_title.pack(pady=(0, 15))

    # 二维码和信息的水平布局
    content_frame = tk.Frame(main_frame, bg='#0d1117')
    content_frame.pack(fill=tk.BOTH, expand=True)

    # 左侧：二维码
    qr_frame = tk.Frame(content_frame, bg='#0d1117')
    qr_frame.pack(side=tk.LEFT, padx=(0, 30))

    qr = qrcode.QRCode(
        version=4,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=12,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#58a6ff", back_color="#0d1117")

    # 放大二维码
    qr_img = qr_img.resize((300, 300), Image.Resampling.LANCZOS)
    qr_photo = ImageTk.PhotoImage(qr_img)
    qr_label = tk.Label(qr_frame, image=qr_photo, bg='#0d1117')
    qr_label.image = qr_photo
    qr_label.pack()

    # 右侧：信息
    info_frame = tk.Frame(content_frame, bg='#0d1117')
    info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # URL
    url_frame = tk.Frame(info_frame, bg='#161b22', relief=tk.FLAT, bd=0)
    url_frame.pack(fill=tk.X, pady=5)

    url_label = tk.Label(url_frame, text="📱 访问地址",
                         font=('Microsoft YaHei', 11),
                         fg='#8b949e', bg='#161b22')
    url_label.pack(pady=(10, 3))

    url_text = tk.Label(url_frame, text=url,
                        font=('Consolas', 15, 'bold'),
                        fg='#f0883e', bg='#161b22')
    url_text.pack(pady=(3, 10))

    # 密码
    pwd_frame = tk.Frame(info_frame, bg='#161b22', relief=tk.FLAT, bd=0)
    pwd_frame.pack(fill=tk.X, pady=5)

    pwd_label = tk.Label(pwd_frame, text="🔐 连接密码",
                         font=('Microsoft YaHei', 11),
                         fg='#8b949e', bg='#161b22')
    pwd_label.pack(pady=(10, 3))

    pwd_text = tk.Label(pwd_frame, text=PASSWORD,
                        font=('Consolas', 16, 'bold'),
                        fg='#3fb950', bg='#161b22')
    pwd_text.pack(pady=(3, 10))

    # 状态
    status_frame = tk.Frame(info_frame, bg='#0d1117')
    status_frame.pack(fill=tk.X, pady=10)

    status_label = tk.Label(status_frame, text="⏳ 等待设备连接...",
                            font=('Microsoft YaHei', 11),
                            fg='#8b949e', bg='#0d1117')
    status_label.pack()

    # 按钮
    btn_frame = tk.Frame(info_frame, bg='#0d1117')
    btn_frame.pack(fill=tk.X, pady=10)

    def on_open_browser():
        webbrowser.open(url)

    def on_copy():
        tk_root.clipboard_clear()
        tk_root.clipboard_append(url)
        copy_btn.config(text="✅ 已复制")
        tk_root.after(2000, lambda: copy_btn.config(text="📋 复制链接"))

    def on_close():
        if tk_root:
            tk_root.destroy()
            os._exit(0)

    browser_btn = tk.Button(btn_frame, text="🌐 浏览器打开",
                            command=on_open_browser,
                            font=('Microsoft YaHei', 10),
                            bg='#238636', fg='white',
                            relief=tk.FLAT, cursor='hand2',
                            padx=20, pady=10)
    browser_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

    copy_btn = tk.Button(btn_frame, text="📋 复制链接",
                         command=on_copy,
                         font=('Microsoft YaHei', 10),
                         bg='#21262d', fg='#c9d1d9',
                         relief=tk.FLAT, cursor='hand2',
                         padx=20, pady=10)
    copy_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

    # 底部关闭按钮
    close_btn = tk.Button(main_frame, text="❌ 关闭程序",
                          command=on_close,
                          font=('Microsoft YaHei', 10),
                          bg='#da3633', fg='white',
                          relief=tk.FLAT, cursor='hand2',
                          padx=20, pady=10)
    close_btn.pack(pady=(15, 0), fill=tk.X)

    hint = tk.Label(main_frame,
                    text="💡 连接后窗口自动关闭\n⚠️ 同一时间只允许一个设备控制 | ⏰ 15秒无操作自动释放",
                    font=('Microsoft YaHei', 9),
                    fg='#8b949e', bg='#0d1117',
                    justify=tk.CENTER)
    hint.pack(pady=(10, 0))

    try:
        tk_root.mainloop()
    except:
        pass


def start_server():
    ip = get_local_ip()
    url = f"http://{ip}"

    print("=" * 50)
    print("🖥️  远程键鼠 v1.0")
    print(f"🔐  密码: {PASSWORD}")
    print(f"📱  地址: {url}")
    print("=" * 50)
    print("📌  触控板操作:")
    print("  👆  滑动 -> 移动鼠标")
    print("  👆  长按500ms(不移动) -> 拖动")
    print("  👆  点击(<500ms) -> 左键")
    print("  👆  长按600ms(不移动) -> 右键")
    print("  🤏  双指捏合/张开 -> Ctrl+/- / Ctrl+=")
    print("  ⬆  三指上滑 -> Win+Tab")
    print("  ⬇  三指下滑 -> Win+D")
    print("=" * 50)
    print("📌  虚拟键盘支持多指同时按组合键")
    print(f"⏰  心跳超时: {HEARTBEAT_TIMEOUT}秒 | 检查间隔: {HEARTBEAT_CHECK_INTERVAL}秒")
    print("=" * 50)
    print("🌐  等待设备连接...")
    print("💡  手机扫码或访问上述地址")
    print("=" * 50)

    qr_thread = threading.Thread(target=show_qr_window, daemon=True)
    qr_thread.start()

    app.run(host='0.0.0.0', port=80, debug=False, threaded=True)

# ============ HTML ============


HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>远程键鼠</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 8px;
            touch-action: none;
            user-select: none;
            height: 100vh;
            overflow: hidden;
        }
        .container {
            max-width: 420px;
            margin: 0 auto;
            height: 100vh;
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        
        .header {
            text-align: center;
            font-size: 16px;
            font-weight: bold;
            color: #58a6ff;
            flex-shrink: 0;
        }
        .header .sub { font-size: 11px; color: #8b949e; font-weight: normal; }
        
        .password-box {
            display: flex;
            gap: 5px;
            flex-shrink: 0;
        }
        .password-box input {
            flex: 1;
            padding: 6px 10px;
            border: 1px solid #30363d;
            border-radius: 6px;
            background: #0d1117;
            color: #c9d1d9;
            font-size: 13px;
        }
        .password-box button {
            padding: 6px 14px;
            border: none;
            border-radius: 6px;
            background: #238636;
            color: white;
            font-size: 13px;
            cursor: pointer;
        }
        .password-box button:active { transform: scale(0.95); }
        .password-box .disconnect-btn {
            background: #da3633;
        }
        
        .touchpad {
            height: 160px;
            flex-shrink: 0;
            background: #161b22;
            border: 2px solid #58a6ff;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            color: #8b949e;
            touch-action: none;
            cursor: grab;
            transition: border-color 0.2s, background 0.2s;
            flex-direction: column;
            gap: 4px;
            position: relative;
        }
        .touchpad:active { cursor: grabbing; }
        .touchpad .hint { 
            pointer-events: none; 
            opacity: 0.3; 
            text-align: center; 
            line-height: 1.6;
            font-size: 11px;
        }
        .touchpad .mode-indicator { 
            pointer-events: none; 
            font-size: 14px;
            font-weight: bold;
            padding: 4px 12px;
            border-radius: 12px;
            background: #1c2333;
            opacity: 0.9;
            color: #58a6ff;
            transition: all 0.2s;
        }
        .touchpad .finger-count {
            pointer-events: none;
            font-size: 12px;
            color: #3fb950;
            opacity: 0.8;
            position: absolute;
            top: 8px;
            right: 12px;
        }
        .touchpad .status-icon {
            pointer-events: none;
            font-size: 20px;
            position: absolute;
            top: 8px;
            left: 12px;
            transition: all 0.2s;
        }
        .touchpad .drag-progress {
            pointer-events: none;
            position: absolute;
            bottom: 8px;
            left: 50%;
            transform: translateX(-50%);
            height: 3px;
            width: 0%;
            background: #d29922;
            border-radius: 2px;
            transition: width 0.1s linear;
            opacity: 0;
        }
        .touchpad .drag-progress.active { opacity: 1; }
        .touchpad .drag-progress.ready { background: #3fb950; width: 100%; }
        .touchpad.dragging { 
            border-color: #d29922; 
            background: #1c1a14;
        }
        .touchpad.dragging .mode-indicator { color: #d29922; }
        .touchpad.locked {
            border-color: #da3633;
            background: #1c1414;
            cursor: not-allowed;
        }
        .touchpad.locked .mode-indicator { color: #da3633; }
        
        .btn-row {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 4px;
            flex-shrink: 0;
        }
        .btn-row button {
            padding: 10px 0;
            border: none;
            border-radius: 6px;
            font-size: 13px;
            background: #21262d;
            color: #c9d1d9;
            cursor: pointer;
            touch-action: manipulation;
        }
        .btn-row button:active { transform: scale(0.92); background: #30363d; }
        .btn-row .g { background: #238636; color: white; }
        .btn-row .r { background: #da3633; color: white; }
        .btn-row .o { background: #d29922; color: white; }
        .btn-row .b { background: #1f6feb; color: white; }
        
        .input-row {
            display: flex;
            gap: 4px;
            flex-shrink: 0;
        }
        .input-row input {
            flex: 1;
            padding: 8px 10px;
            border: 1px solid #30363d;
            border-radius: 6px;
            background: #0d1117;
            color: #c9d1d9;
            font-size: 14px;
        }
        .input-row button {
            padding: 8px 14px;
            border: none;
            border-radius: 6px;
            background: #238636;
            color: white;
            font-size: 14px;
            cursor: pointer;
        }
        .input-row button:active { transform: scale(0.95); }
        
        .kb-toggle {
            padding: 6px;
            border: none;
            border-radius: 6px;
            background: #21262d;
            color: #58a6ff;
            font-size: 13px;
            cursor: pointer;
            flex-shrink: 0;
        }
        .kb-toggle:active { transform: scale(0.95); background: #30363d; }
        
        .kb-wrap {
            overflow: hidden;
            max-height: 0;
            transition: max-height 0.2s ease;
            flex-shrink: 0;
        }
        .kb-wrap.open { max-height: 230px; }
        
        .kb { padding: 3px 0; touch-action: none; }
        .kb-row {
            display: flex;
            gap: 3px;
            margin-bottom: 3px;
            justify-content: center;
        }
        .kb-key {
            flex: 1;
            padding: 8px 0;
            border: 2px solid #30363d;
            border-radius: 4px;
            background: #21262d;
            color: #c9d1d9;
            font-size: 11px;
            cursor: pointer;
            touch-action: none;
            text-align: center;
            min-width: 20px;
            transition: all 0.1s;
            -webkit-touch-callout: none;
        }
        .kb-key:active { transform: scale(0.95); }
        .kb-key.pressed {
            background: #58a6ff;
            color: #0d1117;
            border-color: #58a6ff;
            transform: scale(0.95);
        }
        .kb-key.w1 { flex: 1.5; }
        .kb-key.w2 { flex: 2; }
        .kb-key.w3 { flex: 3.5; }
        .kb-key.sp { background: #1c2333; color: #8b949e; font-size: 10px; }
        .kb-key.sp.pressed { background: #58a6ff; color: #0d1117; }
        
        .status {
            text-align: center;
            font-size: 11px;
            color: #8b949e;
            flex-shrink: 0;
            padding: 3px 0;
        }
        .status .on { color: #3fb950; }
        .status .off { color: #f85149; }
        .status .lock { color: #d29922; }

        .gesture-hint {
            display: none;
            position: absolute;
            bottom: 8px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 11px;
            color: #3fb950;
            background: #1c2333;
            padding: 2px 12px;
            border-radius: 10px;
            opacity: 0.9;
            pointer-events: none;
            white-space: nowrap;
        }
        .gesture-hint.show { display: block; }
        
        .combo-display {
            text-align: center;
            font-size: 12px;
            color: #58a6ff;
            flex-shrink: 0;
            min-height: 20px;
            padding: 2px;
            background: #161b22;
            border-radius: 4px;
            border: 1px solid #30363d;
        }
        .combo-display .keys { color: #f0883e; font-weight: bold; }

        .func-row {
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 4px;
            flex-shrink: 0;
        }
        .func-row button {
            padding: 6px 0;
            border: none;
            border-radius: 4px;
            font-size: 11px;
            background: #21262d;
            color: #c9d1d9;
            cursor: pointer;
            touch-action: manipulation;
        }
        .func-row button:active { transform: scale(0.92); background: #30363d; }
        .func-row .f { background: #1c2333; color: #8b949e; }
        
        .lock-overlay {
            display: none;
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.6);
            border-radius: 10px;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            gap: 8px;
            pointer-events: none;
        }
        .lock-overlay.show { display: flex; }
        .lock-overlay .lock-icon { font-size: 40px; }
        .lock-overlay .lock-text { 
            font-size: 14px; 
            color: #f85149;
            font-weight: bold;
            text-align: center;
            padding: 0 20px;
        }
        .lock-overlay .lock-sub {
            font-size: 11px;
            color: #8b949e;
            text-align: center;
            padding: 0 20px;
        }
        
        .toast {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0,0,0,0.85);
            color: white;
            padding: 20px 30px;
            border-radius: 12px;
            font-size: 14px;
            z-index: 999;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.3s;
            text-align: center;
            max-width: 80%;
            border: 1px solid #30363d;
        }
        .toast.show { opacity: 1; }
        .toast.success { border-color: #3fb950; }
        .toast.error { border-color: #f85149; }
        .toast .toast-sub { font-size: 12px; color: #8b949e; margin-top: 4px; }
    </style>
</head>
<body>

<div class="toast" id="toast">
    <div id="toastMsg">消息</div>
    <div class="toast-sub" id="toastSub"></div>
</div>

<div class="container">
    <div class="header">🖥️ 远程键鼠 <span class="sub">v1.0</span></div>
    
    <div class="password-box">
        <input type="password" id="pwd" placeholder="密码" value="">
        <button onclick="doConnect()" id="connectBtn">连接</button>
        <button onclick="doDisconnect()" class="disconnect-btn" id="disconnectBtn" style="display:none">断开</button>
    </div>
    
    <div class="touchpad" id="tp">
        <span class="status-icon" id="statusIcon">🖱️</span>
        <span class="finger-count" id="fingerCount">👆 0</span>
        <span class="mode-indicator" id="modeIndicator">🖱️ 移动</span>
        <span class="hint">👆 滑动移动 · 长按500ms拖动 · 点击左键 · 长按右键 · 双指滚动</span>
        <span class="gesture-hint" id="gestureHint">手势识别中...</span>
        <span class="drag-progress" id="dragProgress"></span>
        <div class="lock-overlay" id="lockOverlay">
            <span class="lock-icon">🔒</span>
            <span class="lock-text" id="lockText">已被其他设备控制</span>
            <span class="lock-sub" id="lockSub">请等待对方断开或超时</span>
        </div>
    </div>
    
    <div class="combo-display" id="comboDisplay">
        按下的键: <span class="keys" id="pressedKeys">无</span>
    </div>
    
    <div class="func-row">
        <button class="f" onclick="sendAction('key',{key:'escape'})">Esc</button>
        <button class="f" onclick="sendAction('key',{key:'tab'})">Tab</button>
        <button class="f" onclick="sendAction('key',{key:'enter'})">Enter</button>
        <button class="f" onclick="sendAction('key',{key:'backspace'})">⌫</button>
        <button class="f" onclick="sendAction('key',{key:'delete'})">Del</button>
        <button class="f" onclick="sendAction('key',{key:'insert'})">Ins</button>
    </div>
    <div class="func-row">
        <button class="f" onclick="sendAction('key',{key:'home'})">Home</button>
        <button class="f" onclick="sendAction('key',{key:'end'})">End</button>
        <button class="f" onclick="sendAction('key',{key:'pageup'})">PgUp</button>
        <button class="f" onclick="sendAction('key',{key:'pagedown'})">PgDn</button>
        <button class="f" onclick="sendAction('key',{key:'printscreen'})">PrtSc</button>
        <button class="f" onclick="sendAction('key',{key:'pause'})">Pause</button>
    </div>
    
    <div class="btn-row">
        <button class="b" onclick="sendCombo(['ctrl','c'])">Ctrl+C</button>
        <button class="b" onclick="sendCombo(['ctrl','v'])">Ctrl+V</button>
        <button class="b" onclick="sendCombo(['ctrl','a'])">Ctrl+A</button>
        <button class="b" onclick="sendCombo(['ctrl','space'])">Ctrl+Space</button>
        <button class="b" onclick="sendCombo(['win','d'])">Win+D</button>
    </div>
    
    <div class="btn-row">
        <button onclick="sendAction('click')">左键</button>
        <button onclick="sendAction('right_click')">右键</button>
        <button onclick="sendAction('dclick')">双击</button>
        <button class="o" onclick="sendAction('scroll',{amount:3})">⬆</button>
        <button class="o" onclick="sendAction('scroll',{amount:-3})">⬇</button>
    </div>
    <div class="btn-row">
        <button onclick="sendAction('key',{key:'up'})">⬆</button>
        <button onclick="sendAction('key',{key:'down'})">⬇</button>
        <button onclick="sendAction('key',{key:'left'})">⬅</button>
        <button onclick="sendAction('key',{key:'right'})">➡</button>
        <button onclick="sendAction('key',{key:'space'})">␣</button>
    </div>
    
    <div class="input-row">
        <input type="text" id="txt" placeholder="输入文字">
        <button onclick="sendText()">发送</button>
    </div>
    
    <button class="kb-toggle" onclick="toggleKB()">⌨️ 展开键盘 (支持多指同时按)</button>
    <div class="kb-wrap" id="kbw">
        <div class="kb" id="keyboard">
            <div class="kb-row">
                <button class="kb-key sp w1" data-key="`">`</button>
                <button class="kb-key" data-key="1">1</button>
                <button class="kb-key" data-key="2">2</button>
                <button class="kb-key" data-key="3">3</button>
                <button class="kb-key" data-key="4">4</button>
                <button class="kb-key" data-key="5">5</button>
                <button class="kb-key" data-key="6">6</button>
                <button class="kb-key" data-key="7">7</button>
                <button class="kb-key" data-key="8">8</button>
                <button class="kb-key" data-key="9">9</button>
                <button class="kb-key" data-key="0">0</button>
                <button class="kb-key sp w1" data-key="-">-</button>
                <button class="kb-key sp w1" data-key="=">=</button>
                <button class="kb-key sp w1" data-key="backspace">⌫</button>
            </div>
            <div class="kb-row">
                <button class="kb-key sp w1" data-key="tab">Tab</button>
                <button class="kb-key" data-key="q">Q</button>
                <button class="kb-key" data-key="w">W</button>
                <button class="kb-key" data-key="e">E</button>
                <button class="kb-key" data-key="r">R</button>
                <button class="kb-key" data-key="t">T</button>
                <button class="kb-key" data-key="y">Y</button>
                <button class="kb-key" data-key="u">U</button>
                <button class="kb-key" data-key="i">I</button>
                <button class="kb-key" data-key="o">O</button>
                <button class="kb-key" data-key="p">P</button>
                <button class="kb-key sp w1" data-key="[">[</button>
                <button class="kb-key sp w1" data-key="]">]</button>
                <button class="kb-key sp w1" data-key="\\\\">\\\\</button>
            </div>
            <div class="kb-row">
                <button class="kb-key sp w1" data-key="capslock">⇪</button>
                <button class="kb-key" data-key="a">A</button>
                <button class="kb-key" data-key="s">S</button>
                <button class="kb-key" data-key="d">D</button>
                <button class="kb-key" data-key="f">F</button>
                <button class="kb-key" data-key="g">G</button>
                <button class="kb-key" data-key="h">H</button>
                <button class="kb-key" data-key="j">J</button>
                <button class="kb-key" data-key="k">K</button>
                <button class="kb-key" data-key="l">L</button>
                <button class="kb-key sp w1" data-key=";">;</button>
                <button class="kb-key sp w1" data-key="'">'</button>
                <button class="kb-key sp w2" data-key="enter">↵</button>
            </div>
            <div class="kb-row">
                <button class="kb-key sp w1" data-key="shift">⇧</button>
                <button class="kb-key" data-key="z">Z</button>
                <button class="kb-key" data-key="x">X</button>
                <button class="kb-key" data-key="c">C</button>
                <button class="kb-key" data-key="v">V</button>
                <button class="kb-key" data-key="b">B</button>
                <button class="kb-key" data-key="n">N</button>
                <button class="kb-key" data-key="m">M</button>
                <button class="kb-key sp w1" data-key=",">,</button>
                <button class="kb-key sp w1" data-key=".">.</button>
                <button class="kb-key sp w1" data-key="/">/</button>
                <button class="kb-key sp w1" data-key="shift">⇧</button>
            </div>
            <div class="kb-row">
                <button class="kb-key sp" data-key="ctrl">Ctrl</button>
                <button class="kb-key sp" data-key="win">⊞</button>
                <button class="kb-key sp" data-key="alt">Alt</button>
                <button class="kb-key w3" data-key="space">␣</button>
                <button class="kb-key sp" data-key="alt">Alt</button>
                <button class="kb-key sp" data-key="win">⊞</button>
                <button class="kb-key sp" data-key="ctrl">Ctrl</button>
            </div>
        </div>
    </div>
    
    <div class="status" id="st">⚪ 未连接</div>
</div>

<script>
let pwd = '', connected = false, kbOpen = false;
let heartbeatTimer = null;
let reconnectTimer = null;
let deviceName = '';
let isLocked = false;

// ===== Toast =====
function showToast(msg, sub, type) {
    const toast = document.getElementById('toast');
    const msgEl = document.getElementById('toastMsg');
    const subEl = document.getElementById('toastSub');
    msgEl.textContent = msg;
    subEl.textContent = sub || '';
    toast.className = 'toast show ' + (type || '');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// ===== 从 URL 获取密码 =====
function getUrlParam(name) {
    const params = new URLSearchParams(window.location.search);
    return params.get(name);
}

// ===== 获取设备名称 =====
function getDeviceName() {
    const ua = navigator.userAgent;
    if (/iPhone|iPad|iPod/.test(ua)) return 'iPhone';
    if (/Android/.test(ua)) return 'Android';
    if (/Windows/.test(ua)) return 'Windows PC';
    return '浏览器';
}

// ===== 连接/断开 =====
function doConnect() {
    pwd = document.getElementById('pwd').value;
    if (!pwd) {
        showToast('⚠️ 请输入密码', '', 'error');
        return;
    }
    deviceName = getDeviceName();
    
    fetch('/api/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pwd, action: 'connect', name: deviceName })
    })
    .then(res => res.json().then(data => ({ status: res.status, data })))
    .then(({ status, data }) => {
        if (status === 200) {
            connected = true;
            isLocked = false;
            document.getElementById('st').innerHTML = '🟢 已连接';
            document.getElementById('st').className = 'status on';
            document.getElementById('lockOverlay').classList.remove('show');
            document.getElementById('tp').classList.remove('locked');
            document.getElementById('connectBtn').style.display = 'none';
            document.getElementById('disconnectBtn').style.display = 'inline';
            showToast('✅ 连接成功！', '设备: ' + deviceName, 'success');
            
            if (heartbeatTimer) clearInterval(heartbeatTimer);
            heartbeatTimer = setInterval(doHeartbeat, 3000);
        } else {
            showToast('❌ ' + (data.msg || '连接失败'), '', 'error');
            if (status === 403) {
                isLocked = true;
                document.getElementById('lockOverlay').classList.add('show');
                document.getElementById('lockText').textContent = '🔒 ' + (data.msg || '已被其他设备控制');
                document.getElementById('lockSub').textContent = '⏰ 等待对方断开或15秒超时自动释放';
                document.getElementById('tp').classList.add('locked');
                document.getElementById('st').innerHTML = '🔒 被占用';
                document.getElementById('st').className = 'status lock';
                startReconnect();
            }
        }
    })
    .catch(err => {
        showToast('❌ 连接失败', err.message, 'error');
    });
}

function doDisconnect() {
    if (!connected) return;
    fetch('/api/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pwd, action: 'disconnect' })
    }).catch(() => {});
    
    connected = false;
    if (heartbeatTimer) {
        clearInterval(heartbeatTimer);
        heartbeatTimer = null;
    }
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    document.getElementById('st').innerHTML = '⚪ 已断开';
    document.getElementById('st').className = 'status';
    document.getElementById('connectBtn').style.display = 'inline';
    document.getElementById('disconnectBtn').style.display = 'none';
    document.getElementById('lockOverlay').classList.remove('show');
    document.getElementById('tp').classList.remove('locked');
    isLocked = false;
    showToast('🔌 已断开连接', '', '');
}

function startReconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
        if (!connected) {
            showToast('🔄 尝试重新连接...', '', '');
            doConnect();
        }
    }, 5000);
}

function doHeartbeat() {
    if (!connected) return;
    fetch('/api/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pwd, action: 'heartbeat' })
    })
    .then(res => {
        if (!res.ok) {
            connected = false;
            if (heartbeatTimer) {
                clearInterval(heartbeatTimer);
                heartbeatTimer = null;
            }
            document.getElementById('st').innerHTML = '🔴 连接断开';
            document.getElementById('st').className = 'status off';
            document.getElementById('connectBtn').style.display = 'inline';
            document.getElementById('disconnectBtn').style.display = 'none';
            showToast('❌ 连接已断开', '请重新连接', 'error');
            startReconnect();
        }
        return res.json();
    })
    .catch(() => {
        if (connected) {
            connected = false;
            if (heartbeatTimer) {
                clearInterval(heartbeatTimer);
                heartbeatTimer = null;
            }
            document.getElementById('st').innerHTML = '🔴 连接丢失';
            document.getElementById('st').className = 'status off';
            document.getElementById('connectBtn').style.display = 'inline';
            document.getElementById('disconnectBtn').style.display = 'none';
            showToast('❌ 连接丢失', '尝试重新连接...', 'error');
            startReconnect();
        }
    });
}

// ===== 键盘状态 =====
let pressedKeys = {};
let touchStartTime = 0, touchStartX = 0, touchStartY = 0;
let touchMoved = false, isDragging = false;
let dragTimer = null, longPressTimer = null;
let touchStartPositions = {}, lastGesture = '', gestureTimeout = null;

function toggleKB() {
    kbOpen = !kbOpen;
    document.getElementById('kbw').classList.toggle('open', kbOpen);
    document.querySelector('.kb-toggle').textContent = kbOpen ? '⌨️ 收起键盘 (支持多指同时按)' : '⌨️ 展开键盘 (支持多指同时按)';
}

async function sendAction(action, extra = {}) {
    if (!connected) {
        showToast('⚠️ 未连接', '请先连接', 'error');
        return;
    }
    if (isLocked) {
        showToast('🔒 被锁定', '无法操作', 'error');
        return;
    }
    try {
        const res = await fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: pwd, action, ...extra })
        });
        const data = await res.json();
        if (!res.ok) {
            if (res.status === 401 || res.status === 403) {
                connected = false;
                if (heartbeatTimer) {
                    clearInterval(heartbeatTimer);
                    heartbeatTimer = null;
                }
                document.getElementById('st').innerHTML = '🔴 连接失效';
                document.getElementById('st').className = 'status off';
                document.getElementById('connectBtn').style.display = 'inline';
                document.getElementById('disconnectBtn').style.display = 'none';
                showToast('❌ ' + (data.msg || '连接失效'), '请重新连接', 'error');
                startReconnect();
            }
            throw new Error(data.msg || '请求失败');
        }
        return data;
    } catch(e) {
        console.error(e);
        throw e;
    }
}

function sendCombo(keys) {
    sendAction('key_combination', { keys: keys }).catch(() => {});
}

// ===== 键盘多指 =====
function updateComboDisplay() {
    const keys = Object.keys(pressedKeys);
    const display = document.getElementById('pressedKeys');
    display.textContent = keys.length === 0 ? '无' : keys.join(' + ');
    display.style.color = keys.length === 0 ? '#8b949e' : '#f0883e';
}

function keyPress(key) {
    if (!key || !connected || isLocked) return;
    if (pressedKeys[key]) return;
    pressedKeys[key] = true;
    updateComboDisplay();
    document.querySelectorAll('.kb-key').forEach(el => {
        if (el.dataset.key === key) el.classList.add('pressed');
    });
    sendAction('key_down', { key: key }).catch(() => {});
}

function keyRelease(key) {
    if (!key) return;
    if (!pressedKeys[key]) return;
    delete pressedKeys[key];
    updateComboDisplay();
    document.querySelectorAll('.kb-key').forEach(el => {
        if (el.dataset.key === key) el.classList.remove('pressed');
    });
    sendAction('key_up', { key: key }).catch(() => {});
}

function releaseAllKeys() {
    const keys = Object.keys(pressedKeys);
    for (const key of keys) {
        delete pressedKeys[key];
        document.querySelectorAll('.kb-key').forEach(el => {
            if (el.dataset.key === key) el.classList.remove('pressed');
        });
        sendAction('key_up', { key: key }).catch(() => {});
    }
    updateComboDisplay();
}

document.querySelectorAll('.kb-key').forEach(el => {
    const key = el.dataset.key;
    if (!key) return;
    el.addEventListener('mousedown', (e) => { e.preventDefault(); keyPress(key); });
    el.addEventListener('mouseup', (e) => { e.preventDefault(); keyRelease(key); });
    el.addEventListener('mouseleave', () => { keyRelease(key); });
    el.addEventListener('touchstart', (e) => { e.preventDefault(); keyPress(key); }, { passive: false });
    el.addEventListener('touchend', (e) => { e.preventDefault(); keyRelease(key); }, { passive: false });
    el.addEventListener('touchcancel', (e) => { e.preventDefault(); keyRelease(key); }, { passive: false });
});
document.getElementById('keyboard').addEventListener('touchcancel', releaseAllKeys);

// ===== 触控板 =====
const tp = document.getElementById('tp');
const dragProgress = document.getElementById('dragProgress');

function getDistance(t1, t2) {
    return Math.sqrt(Math.pow(t1.clientX - t2.clientX, 2) + Math.pow(t1.clientY - t2.clientY, 2));
}

function getSwipeDirection(sx, sy, ex, ey) {
    const dx = ex - sx, dy = ey - sy;
    if (Math.abs(dx) < 30 && Math.abs(dy) < 30) return 'tap';
    return Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up');
}

function handleMultiTouch(touches) {
    const count = touches.length;
    document.getElementById('fingerCount').textContent = '👆 ' + count;
    if (count === 0 || !connected || isLocked) return;
    
    // ===== 双指 ===== 滚动
    if (count === 2) {
        const t1 = touches[0], t2 = touches[1];
        const midY = (t1.clientY + t2.clientY) / 2;
        
        if (!touchStartPositions['2f']) {
            touchStartPositions['2f'] = { y: midY };
            return;
        }
        
        const deltaY = midY - touchStartPositions['2f'].y;
        const threshold = 30;
        
        if (Math.abs(deltaY) > threshold) {
            const amount = deltaY > 0 ? -5 : 5;
            sendAction('scroll', { amount: amount }).catch(() => {});
            showGestureHint(deltaY > 0 ? '⬇ 双指下滑' : '⬆ 双指上滑');
            touchStartPositions['2f'].y = midY;
        }
        return;
    }
    
    // ===== 三指 ===== 系统手势
    if (count === 3) {
        const arr = Array.from(touches);
        const avgX = arr.reduce((s, t) => s + t.clientX, 0) / 3;
        const avgY = arr.reduce((s, t) => s + t.clientY, 0) / 3;
        if (!touchStartPositions['3f']) { touchStartPositions['3f'] = { x: avgX, y: avgY }; return; }
        const dx = avgX - touchStartPositions['3f'].x;
        const dy = avgY - touchStartPositions['3f'].y;
        if (Math.abs(dx) > 50 || Math.abs(dy) > 50) {
            const dir = getSwipeDirection(touchStartPositions['3f'].x, touchStartPositions['3f'].y, avgX, avgY);
            const key = '3f_' + dir;
            if (lastGesture !== key) {
                if (dir === 'up') {
                    sendAction('multi_touch', { gesture: 'three_finger_swipe_up' }).catch(() => {});
                    showGestureHint('⬆ 三指上滑 - 任务视图');
                } else if (dir === 'down') {
                    sendAction('multi_touch', { gesture: 'three_finger_swipe_down' }).catch(() => {});
                    showGestureHint('⬇ 三指下滑 - 显示桌面');
                }
                lastGesture = key;
            }
        }
        return;
    }
}

function showGestureHint(text) {
    const hint = document.getElementById('gestureHint');
    hint.textContent = text;
    hint.classList.add('show');
    clearTimeout(gestureTimeout);
    gestureTimeout = setTimeout(() => hint.classList.remove('show'), 1200);
}

function updateDragProgress(elapsed) {
    const p = Math.min(elapsed / 500, 1);
    dragProgress.style.width = (p * 100) + '%';
    dragProgress.classList.toggle('ready', p >= 1);
}

tp.addEventListener('touchstart', (e) => {
    e.preventDefault();
    if (!connected || isLocked) return;
    const touches = e.touches, count = touches.length;
    document.getElementById('fingerCount').textContent = '👆 ' + count;
    
    // 多指直接交给 handleMultiTouch
    if (count >= 2) {
        clearTimeout(longPressTimer); clearTimeout(dragTimer);
        dragProgress.classList.remove('active', 'ready');
        dragProgress.style.width = '0%';
        handleMultiTouch(touches);
        return;
    }
    
    // 单指
    if (count === 1) {
        const t = touches[0];
        touchStartX = t.clientX; touchStartY = t.clientY;
        touchStartTime = Date.now();
        touchMoved = false; isDragging = false;
        document.getElementById('statusIcon').textContent = '🖱️';
        tp.classList.remove('dragging');
        document.getElementById('modeIndicator').textContent = '🖱️ 移动';
        dragProgress.classList.remove('active', 'ready');
        dragProgress.style.width = '0%';
        
        clearTimeout(longPressTimer);
        longPressTimer = setTimeout(() => {
            if (!touchMoved) {
                sendAction('right_click').catch(() => {});
                showGestureHint('🖱️ 右键');
                if (navigator.vibrate) navigator.vibrate(20);
                touchMoved = true;
            }
        }, 600);
        
        clearTimeout(dragTimer);
        dragTimer = setTimeout(() => {
            if (!touchMoved) {
                dragProgress.classList.add('active');
                document.getElementById('statusIcon').textContent = '⏳';
                document.getElementById('modeIndicator').textContent = '⏳ 拖动待命';
                showGestureHint('⏳ 拖动待命...');
                dragTimer = setTimeout(() => {
                    if (!touchMoved) {
                        isDragging = true;
                        document.getElementById('statusIcon').textContent = '✋';
                        tp.classList.add('dragging');
                        document.getElementById('modeIndicator').textContent = '✋ 拖动';
                        dragProgress.classList.add('ready');
                        showGestureHint('✋ 拖动模式');
                        sendAction('drag', { dx: 1, dy: 1 }).catch(() => {});
                    }
                }, 100);
            }
        }, 500);
    }
}, { passive: false });

tp.addEventListener('touchmove', (e) => {
    e.preventDefault();
    if (!connected || isLocked) return;
    const touches = e.touches, count = touches.length;
    document.getElementById('fingerCount').textContent = '👆 ' + count;
    
    if (count >= 2) {
        clearTimeout(longPressTimer); clearTimeout(dragTimer);
        dragProgress.classList.remove('active', 'ready');
        dragProgress.style.width = '0%';
        handleMultiTouch(touches);
        return;
    }
    
    if (count === 1) {
        const t = touches[0];
        let dx = (t.clientX - touchStartX) * 2;
        let dy = (t.clientY - touchStartY) * 2;
        
        if (Math.abs(dx) < 3 && Math.abs(dy) < 3) {
            if (!isDragging) updateDragProgress(Date.now() - touchStartTime);
            return;
        }
        
        if (!touchMoved) {
            touchMoved = true;
            clearTimeout(longPressTimer); clearTimeout(dragTimer);
            if (!isDragging) {
                dragProgress.classList.remove('active', 'ready');
                dragProgress.style.width = '0%';
            }
        }
        
        if (isDragging) {
            sendAction('drag', { dx, dy }).catch(() => {});
        } else {
            sendAction('move_relative', { dx, dy }).catch(() => {});
        }
        touchStartX = t.clientX; touchStartY = t.clientY;
    }
}, { passive: false });

tp.addEventListener('touchend', (e) => {
    e.preventDefault();
    const remaining = e.touches, count = remaining.length;
    document.getElementById('fingerCount').textContent = '👆 ' + count;
    clearTimeout(longPressTimer); clearTimeout(dragTimer);
    dragProgress.classList.remove('active', 'ready');
    dragProgress.style.width = '0%';
    
    if (count === 0 && !isLocked) {
        const elapsed = Date.now() - touchStartTime;
        if (!touchMoved && !isDragging && elapsed < 500) {
            sendAction('click').catch(() => {});
            showGestureHint('🖱️ 左键');
            if (navigator.vibrate) navigator.vibrate(10);
        }
        touchMoved = false; isDragging = false;
        document.getElementById('statusIcon').textContent = '🖱️';
        tp.classList.remove('dragging');
        document.getElementById('modeIndicator').textContent = '🖱️ 移动';
        touchStartPositions = {}; lastGesture = '';
        setTimeout(() => document.getElementById('gestureHint').classList.remove('show'), 1000);
    } else if (count === 1 && !isLocked) {
        const t = remaining[0];
        touchStartX = t.clientX; touchStartY = t.clientY;
        touchStartTime = Date.now();
        touchMoved = false; isDragging = false;
        document.getElementById('statusIcon').textContent = '🖱️';
        tp.classList.remove('dragging');
        document.getElementById('modeIndicator').textContent = '🖱️ 移动';
    }
}, { passive: false });

tp.addEventListener('touchcancel', () => {
    clearTimeout(longPressTimer); clearTimeout(dragTimer);
    dragProgress.classList.remove('active', 'ready');
    dragProgress.style.width = '0%';
    touchMoved = false; isDragging = false;
    touchStartPositions = {}; lastGesture = '';
    document.getElementById('fingerCount').textContent = '👆 0';
    document.getElementById('statusIcon').textContent = '🖱️';
    tp.classList.remove('dragging');
    document.getElementById('modeIndicator').textContent = '🖱️ 移动';
});

tp.addEventListener('wheel', (e) => {
    e.preventDefault();
    if (!connected || isLocked) return;
    sendAction('scroll', { amount: e.deltaY > 0 ? -3 : 3 }).catch(() => {});
}, { passive: false });

tp.addEventListener('click', () => {
    if (!connected || isLocked) return;
    sendAction('click').catch(() => {});
});

function sendText() {
    const inp = document.getElementById('txt');
    if (inp.value && connected && !isLocked) {
        sendAction('type', { text: inp.value }).catch(() => {});
        inp.value = '';
    }
}

window.addEventListener('beforeunload', () => {
    if (connected) {
        navigator.sendBeacon('/api/control', JSON.stringify({ password: pwd, action: 'disconnect' }));
    }
});

// ===== 页面加载自动填入密码并连接 =====
(function autoConnect() {
    const pwdParam = getUrlParam('pwd');
    if (pwdParam) {
        document.getElementById('pwd').value = pwdParam;
        // 延迟300ms自动连接，确保页面完全加载
        setTimeout(doConnect, 300);
    } else {
        // 没有密码参数，尝试从 localStorage 恢复
        const saved = localStorage.getItem('saved_pwd');
        if (saved) {
            document.getElementById('pwd').value = saved;
            setTimeout(doConnect, 300);
        }
    }
})();

// 连接成功后保存密码到 localStorage
(function patchConnect() {
    const origConnect = doConnect;
    doConnect = function() {
        const pwdVal = document.getElementById('pwd').value;
        if (pwdVal) {
            localStorage.setItem('saved_pwd', pwdVal);
        }
        origConnect.call(this);
    };
})();

</script>
</body>
</html>
"""

# ============ 主入口 ============


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


if __name__ == '__main__':

    start_server()
