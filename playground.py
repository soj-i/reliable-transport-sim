import struct

import time
from concurrent.futures import ThreadPoolExecutor
import hashlib
import threading
def compute_hash(data) -> bytes:
    return hashlib.md5(data).digest()

class Testing:
    def __init__(self):
        self.timer = time.time() + 5.25


def main():

    time_object = Testing()
    print(f"curr time {time.time()}, timer at : {time_object.timer}")
    
    print("sleeping...")
    time.sleep(6)

    print(f"curr time {time.time()}, timer at : {time_object.timer}")

    time_object.timer+=10

    print(f"curr time {time.time()}, timer now set to : {time_object.timer}")
    
    
    # for i in range(len(tests)):
    #     print(f"test {i+1}:")
    #     seq, ack, flag = struct.unpack("IIB", tests[i])
    #     print(f"seq#: {seq}, ack#: {ack}, flag: {bin(flag)}\n\n")

if __name__ == "__main__":
    main()