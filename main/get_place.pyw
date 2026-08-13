import pygame
import pyautogui
import sys


class MouseTracker:
    def __init__(self):
        pygame.init()

        # 获取屏幕尺寸
        screen_info = pygame.display.Info()
        self.screen_width = screen_info.current_w
        self.screen_height = screen_info.current_h

        # 创建全屏窗口，无边框
        self.screen = pygame.display.set_mode(
            (self.screen_width, self.screen_height),
            pygame.NOFRAME | pygame.SRCALPHA
        )
        pygame.display.set_caption("鼠标追踪器")

        # 设置窗口透明
        self.set_transparent()

        # 红点参数
        self.dot_radius = 8
        self.dot_color = (255, 0, 0, 80)  # 红色

        # 时钟
        self.clock = pygame.time.Clock()

        # 主循环
        self.running = True
        self.run()

    def set_transparent(self):
        """设置窗口透明（Windows）"""
        try:
            import win32gui
            import win32con
            import win32api

            # 获取窗口句柄
            hwnd = pygame.display.get_wm_info()['window']

            # 设置窗口为分层窗口
            win32gui.SetWindowLong(
                hwnd,
                win32con.GWL_EXSTYLE,
                win32gui.GetWindowLong(
                    hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT
            )

            # 设置透明颜色（黑色作为透明色）
            win32gui.SetLayeredWindowAttributes(
                hwnd,
                win32api.RGB(0, 0, 0),
                0,
                win32con.LWA_COLORKEY
            )

            # 让窗口置顶
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
            )

            print("✅ 透明窗口设置成功")
        except Exception as e:
            print(f"⚠️ 透明窗口设置失败: {e}")
            print("程序将继续运行，但背景可能不透明")

    def run(self):
        """主循环"""
        print("🎯 鼠标追踪器已启动")
        print("按 ESC 退出")

        while self.running:
            # 处理事件
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False

            # 清屏（黑色作为透明色）
            self.screen.fill((0, 0, 0))

            # 获取鼠标位置
            x, y = pyautogui.position()

            surface = pygame.Surface((self.dot_radius * 2, self.dot_radius * 2), pygame.SRCALPHA)

            # 绘制红点
            pygame.draw.circle(
                surface,
                self.dot_color,
                (self.dot_radius, self.dot_radius),
                self.dot_radius
            )
            self.screen.blit(surface, (x - self.dot_radius, y - self.dot_radius))
            # 更新显示
            pygame.display.flip()
            self.clock.tick(60)  # 60帧/秒

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    # 检查依赖
    try:
        import pygame
    except ImportError:
        print("请先安装 pygame: pip install pygame")
        exit()

    try:
        import pyautogui
    except ImportError:
        print("请先安装 pyautogui: pip install pyautogui")
        exit()

    MouseTracker()
