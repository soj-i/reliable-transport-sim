import struct

def main():

    
    test1 = struct.pack("IIB", 123, 456, 0)

    test2 = struct.pack("IIB", 123, 456, 1)

    test3 = struct.pack("IIB", 123, 456, 2)

    tests = [test1, test2, test3]

    for i in range(len(tests)):
        print(f"test {i+1}:")
        seq, ack, flag = struct.unpack("IIB", tests[i])
        print(f"seq#: {seq}, ack#: {ack}, flag: {bin(flag)}\n\n")

if __name__ == "__main__":
    main()