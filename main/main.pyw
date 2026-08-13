from get_place import MouseTracker
from start import start_server
import threading
import os
import sys
import os
import sys
import winshell
from winshell import shortcut


def add_to_startup():
    """将当前程序添加到开机自启"""
    try:
        # 获取启动文件夹路径
        startup_folder = winshell.startup()

        # 当前脚本的完整路径
        script_path = os.path.abspath(sys.argv[0])

        # 快捷方式路径
        shortcut_path = os.path.join(startup_folder, "RemoteMouse.lnk")

        # 创建快捷方式（修正参数名）
        with shortcut(shortcut_path) as sc:
            sc.path = script_path
            sc.working_directory = os.path.dirname(script_path)
            sc.icon_location = (script_path, 0)

        print(f"✅ 已添加到开机自启: {shortcut_path}")
        return True
    except Exception as e:
        print(f"❌ 添加失败: {e}")
        return False


def thread1():
    MouseTracker()


def thread2():
    start_server()


add_to_startup()
t1 = threading.Thread(target=thread1)
t2 = threading.Thread(target=thread2)
t1.start()
t2.start()
