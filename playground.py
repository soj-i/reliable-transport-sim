import struct

import hashlib

def compute_hash(data) -> bytes:
    return hashlib.md5(data).digest()

def main():

    
    test1 = struct.pack("IIB", 123, 456, 0)

    test2 = struct.pack("IIB", 123, 456, 1)

    test3 = struct.pack("IIB", 123, 456, 2)

    tests = [test1, test2, test3]

    
    data_stuff = b'"hello"'
    
    print(f"hash of {data_stuff}\n hash: {compute_hash(data_stuff)}\nsize: {(compute_hash(data_stuff))}")

    # for i in range(len(tests)):
    #     print(f"test {i+1}:")
    #     seq, ack, flag = struct.unpack("IIB", tests[i])
    #     print(f"seq#: {seq}, ack#: {ack}, flag: {bin(flag)}\n\n")

if __name__ == "__main__":
    main()