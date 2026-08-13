from get_place import MouseTracker
from start import start_server
import threading


def thread1():
    MouseTracker()


def thread2():
    start_server()


t1 = threading.Thread(target=thread1)
t2 = threading.Thread(target=thread2)
t1.start()
t2.start()
