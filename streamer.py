# do not import anything else from loss_socket besides LossyUDP
from lossy_socket import LossyUDP
# do not import anything else from socket except INADDR_ANY
from socket import INADDR_ANY

from struct import *

from heapq import *
from queue import PriorityQueue

from concurrent.futures import ThreadPoolExecutor
from time import *

class Streamer:
    def __init__(self, dst_ip, dst_port,
                 src_ip=INADDR_ANY, src_port=0):
        """Default values listen on all network interfaces, chooses a random source port,
           and does not introduce any simulated packet loss."""
        self.socket = LossyUDP()
        self.socket.bind((src_ip, src_port))
        self.dst_ip = dst_ip
        self.dst_port = dst_port
        
        self.seq = 0
        self.ack = False

        self.ack_num = 0
        self.receive_buffer = []
        self.expected_seq = 0
        
        self.ack_buffer = []
        self.closed = False
        
        executor = ThreadPoolExecutor(max_workers=1) 
        executor.submit(self.listener)


        """
        CURRENT FLAG BYTE LAYOUT

        1 BYTE -> 8 bits

        7   6   5   4   3   2   1   0
                                    ^
                                     is_acknowledgement - bool [1 bit]
                                ^ is_fin_acknowledgement - bool [1 bit]

        * Rest unused (for now)
        """

    def flag_byte_setter(self, is_acknowledgement = False, is_fin_acknowledgement = False):
        if is_acknowledgement:
            return 2
        if is_fin_acknowledgement:
            return 1
        else:
            return 0 # no flags set - aka data segment
        

    def listener(self):
        # print("listener function")
        # print(f"state of self.closed: {self.closed}")
        while not self.closed: # a later hint will explain self.closed
            try:
                data, addr = self.socket.recvfrom() # header:data (in some order) -> 3:d 1:d 0:d 2:d 4:d
                # if len(data) >= 9:
                seq_num, ack_num, flags = unpack('!II?', data[:9])  # Unpack the first 4 bytes as sequence number -> seq_num : 3

                data_bytes = data[9:]
                is_ack = (flags & 0x1)
                
                if not is_ack: # data segment
                    heappush(self.receive_buffer, (seq_num, data_bytes))

                    ack_packet = pack('!II?', self.seq, seq_num, self.flag_byte_setter(is_acknowledgement=True))
                    self.socket.sendto(ack_packet, (self.dst_ip, self.dst_port))

                else: # acknowledgement
                # set acknowledgement attribute to True to signal sucess to sender
                    self.ack = True
                


            except Exception as e:
                print("listener died!")
                print(e)
    

    def send(self, data_bytes: bytes) -> None:

        """Note that data_bytes can be larger than one packet."""
        """ Allow Streamer#send to support data larger than 1472 bytes.
        Break the data_bytes into chunks and send the data in multiple packets. """
        # Your code goes here!  The code below should be changed!
        # print("send function")
        byte_size = len(data_bytes) 
        max_seg_size = 1472 - 4 - 4 - 1
                        #  (seq)(ack)(flag)

        splits = byte_size // max_seg_size # 6 / 4 -> 1.25
        """
        (6) -> (0:3) (4:5)
        data_bytes ->[0:4] [4:5]
        """

        start = 0

        byte_arr = [] # 
       

        if byte_size > max_seg_size: 
            for _ in range(splits):   #range -> (0,1), runs ONCE
                end = start + max_seg_size # 4 | 6 -> start = 0, end = 4 ... start = 4, end = 8
                byte_arr.append(data_bytes[start:end]) #data_bytes[0:4] -> indices(0:3)
                start = end # start = 4
            # byte_arr = [data_bytes[0:4]]

            if end < byte_size: 
                byte_arr.append(data_bytes[end:byte_size])


            for i in byte_arr:
                header = pack('!II?', self.seq, self.ack_num, 0) # seq #, ack #, flag
                self.seq += 1
                full_packet = header + i
                self.socket.sendto(full_packet,(self.dst_ip, self.dst_port))
                while not self.ack:
                    sleep(0.01) #should stall here
                
                
        else:
            header = pack('!II?', self.seq,self.ack_num,0) 
            self.seq += 1
            full_packet = header + data_bytes 
            self.socket.sendto(full_packet, (self.dst_ip, self.dst_port))
            while not self.ack: # should stall here
                sleep(0.01)
            self.ack = False

    def recv(self) -> bytes:
        """Blocks (waits) if no data is ready to be read from the connection."""
        # queries receive buffer if populated
        complete_data = bytes()
        while True:
            if self.receive_buffer and self.receive_buffer[0][0] == self.expected_seq:
                seq_num, data_bytes = heappop(self.receive_buffer)
                complete_data += data_bytes #  0:d 1:d 2:d 3:d 4:d
                self.expected_seq += 1
                return complete_data


    def close(self) -> None:
        """Cleans up. It should block (wait) until the Streamer is done with all
           the necessary ACKs and retransmissions"""
        # your code goes here, especially after you add ACKs and retransmissions.
        self.closed = True
        self.socket.stoprecv()
