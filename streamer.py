# do not import anything else from loss_socket besides LossyUDP
from lossy_socket import LossyUDP
# do not import anything else from socket except INADDR_ANY
from socket import INADDR_ANY

from struct import pack, unpack
from heapq import *
from concurrent.futures import ThreadPoolExecutor
import time


'''

dictionary - of packets sent but not ack'd

key: seq # val : 

'''
class Streamer:
    def __init__(self, dst_ip, dst_port, src_ip=INADDR_ANY, src_port=0):
        """Default values listen on all network interfaces, chooses a random source port,
           and does not introduce any simulated packet loss."""
        
        self.packet_dict = dict()

        self.socket = LossyUDP()
        self.socket.bind((src_ip, src_port))
        self.dst_ip = dst_ip
        self.dst_port = dst_port
        
        self.seq = 0
        self.ack = False

        self.ack_num = 0
        self.receive_buffer = []
        self.expected_seq = 0
        
        self.fin_ackd = False
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

    def flag_byte_setter(self, is_acknowledgement=False, is_fin_acknowledgement=False):
        if is_acknowledgement:
            return 2
        if is_fin_acknowledgement:
            return 1
        else:
            return 0  # no flags set - aka data segment

    def listener(self):
        while not self.closed:
            try:
                data, addr = self.socket.recvfrom()
                
                seq_num, ack_num, flags = unpack('!II?', data[:9])
                data_bytes = data[9:]

                is_ack = (flags & 0x1) # ack packet found

                is_fin = ((flags >> 1) & 0x1) # FIN packet found

                if not is_ack and not is_fin:  # data segment
                    if seq_num == self.expected_seq:
                        heappush(self.receive_buffer, (seq_num, data_bytes))
                        self.packet_dict[seq_num] = data_bytes
                        ack_packet = pack('!II?', self.seq, seq_num, self.flag_byte_setter(is_acknowledgement=True))
                        self.socket.sendto(ack_packet, (self.dst_ip, self.dst_port))
                        self.expected_seq += 1
                    else:
                        ack_packet = pack('!II?', self.seq, seq_num, self.flag_byte_setter(is_acknowledgement=True))
                        self.socket.sendto(ack_packet, (self.dst_ip, self.dst_port))

                if is_ack:  # acknowledgement
                    self.ack = True
                    self.ack_num = ack_num
                   
                if is_fin:
                    self.fin_ackd = True


            except Exception as e:
                print("listener died!")
                print(e)

    def send(self, data_bytes: bytes) -> None:
        """Note that data_bytes can be larger than one packet."""
        """ Allow Streamer#send to support data larger than 1472 bytes.
        Break the data_bytes into chunks and send the data in multiple packets. """
        byte_size = len(data_bytes)
        max_seg_size = 1472 - 4 - 4 - 1  # 9 bytes for the sequence number, ack number, and flags
        splits = byte_size // max_seg_size
        start = 0
        byte_arr = []

        if byte_size > max_seg_size:
            for _ in range(splits):
                end = start + max_seg_size
                byte_arr.append(data_bytes[start:end])
                start = end
            if end < byte_size:
                byte_arr.append(data_bytes[end:byte_size])

            for i in byte_arr:
                header = pack('!II?', self.seq, self.ack_num, 0)  # seq, ack, flag
                full_packet = header + i
                while True:
                    stalling = time.time() + 0.25  # Set timeout for 0.25 seconds
                    self.socket.sendto(full_packet, (self.dst_ip, self.dst_port))
                    while time.time() < stalling:
                        if self.ack and self.ack_num == self.seq:
                            break
                        time.sleep(0.01)  # Stall here
                    if self.ack and self.ack_num == self.seq:
                        self.ack = False  # Reset ack flag for the next packet
                        break  # Exit the loop if ACK is received
                self.seq += 1  # only increment seq IFF ack has been received
        else:
            header = pack('!II?', self.seq, self.ack_num, 0)
            full_packet = header + data_bytes

            while True:
                stalling = time.time() + 0.25  # Set timeout for 0.25 seconds
                self.socket.sendto(full_packet, (self.dst_ip, self.dst_port))

                while time.time() < stalling:
                    if self.ack and self.ack_num == self.seq:
                        break
                    time.sleep(0.01)  # Stall here
                if self.ack and self.ack_num == self.seq:
                    # print(f"ack True and seq / ack num = {self.seq}")
                    self.ack = False  # Reset ack flag for the next packet
                    break  # Exit the loop if ACK is received
                else:
                    print(f"packet loss, resending {self.seq}")
                    # self.expected_seq -= 1
            self.seq += 1  # only increment seq IFF ack has been received

    def recv(self) -> bytes:
        """Blocks (waits) if no data is ready to be read from the connection."""
        print("recv entered")
        complete_data = bytes()
        while len(self.receive_buffer) == 0:
            time.sleep(0.01)

        while self.receive_buffer:
            print(f"buffer state: {self.receive_buffer}")
            # print(f"state of receive buffer: {self.receive_buffer}\n expecting: {self.expected_seq}")
            seq_num, data_bytes = heappop(self.receive_buffer)

            complete_data += data_bytes # 0:d 1:d 2:d 3:d 4:d
        
        
        print(f"data to server: {complete_data}")
        return complete_data
        # time.sleep(0.01)  # Prevent busy waiting


    def close(self) -> None:
        """Cleans up. It should block (wait) until the Streamer is done with all
           the necessary ACKs and retransmissions"""
        
        while self.seq != self.ack_num: # finishes transmission
            print(f"seq num {self.seq} \n ack num {self.ack_num}")
            time.sleep(0.01)

        # now that transmission is done, create fin packet, send, and start timer
        while True:
            fin_packet = pack('!II?', self.seq, self.ack_num, self.flag_byte_setter(is_fin_acknowledgement=True))
            self.socket.sendto(fin_packet,(self.dst_ip, self.dst_port))
            stalling = time.time() + 0.25
            
            # check if fin packet has been ack'd
            while time.time() < stalling:
                if self.fin_ackd: # FIN acknowledged
                    break # break out of stal
                time.sleep(0.01)

            if self.fin_ackd: # FIN acknowledged
                break # break out of all loops

        #     else re-loop over fin packet creation logic
        # fin ack received
        time.sleep(2) #wait 2 seconds before closing
        
        self.closed = True
        self.socket.stoprecv()