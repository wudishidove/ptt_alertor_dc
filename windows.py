import subprocess
import threading
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw

def run_bat():
    subprocess.Popen(
        r"D:\OneDrive\code\mygithub\ptt_alertor_dc\windows_run.bat",
        creationflags=subprocess.CREATE_NO_WINDOW
    )

def on_exit(icon, item):
    icon.stop()

def create_icon():
    # 建立簡單的黑白圖示


    icon = Icon("PTT Alertor")
    icon.icon = Image.open("logo.jpg")
    icon.menu = Menu(
        MenuItem("退出", on_exit)
    )
    icon.title = "PTT Alertor"
    run_thread = threading.Thread(target=run_bat)
    run_thread.start()
    icon.run()
if __name__ == "__main__":
    create_icon()

