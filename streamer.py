# do not import anything else from loss_socket besides LossyUDP
from lossy_socket import LossyUDP
# do not import anything else from socket except INADDR_ANY
from socket import INADDR_ANY

import struct
from heapq import *
from concurrent.futures import ThreadPoolExecutor
import time
import hashlib
from threading import Lock

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
        self.timer = time.time() + 0.50


        self.ack_num = 0
        self.receive_buffer = []
        self.send_buffer = []
        self.expected_seq = 0
        
        self.fin_ackd = False
        self.fin = False
        self.closed = False
        
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(self.listener)

        self.lock = Lock()
        self.timer = time.time()
        self.unacknowledged_packets = {}

        """
        CURRENT FLAG BYTE LAYOUT

        1 BYTE -> 8 bits

        7   6   5   4   3   2   1   0
                                    ^
                                     is_acknowledgement - bool [1 bit]
                                ^ is_fin_acknowledgement - bool [1 bit]

        * Rest unused (for now)
        """

    def compute_hash(self, data) -> bytes:
        return hashlib.md5(data).digest()
    
    def packet_checksummer(self, packet) -> bytes:
        # packet = header + data

        full_checksum_field = self.compute_hash(packet)
        four_checksum_bytes = full_checksum_field[:4]
        header = packet[:9]
        body = packet[9:]
        
        final_packet = header + four_checksum_bytes + body
        # one packet = [header checksum data_bytes]
        return final_packet

    def flag_byte_setter(self, is_acknowledgement=False, is_fin_packet = False, is_fin_acknowledgement=False):
        flag = 0
        if is_acknowledgement:
            flag |= 0x1  # Set the least significant bit for ACK
        if is_fin_packet:
            flag |= 0x2  # Set the second least significant bit for FIN
        if is_fin_acknowledgement:
            flag |= 0x4
        return flag

    def valid_checksum_checker(self, data) -> bool:
        '''
        header + checksum + body -> hash(header+body) == checksum?, return bool
        '''

        header_minus_check =  data[:9]
        maybe_checksum = data[9:13]
        body_minus_check = data[13:]

        packet_without_checksum = header_minus_check + body_minus_check
        computed_checksum = self.compute_hash(packet_without_checksum)[:4]

        if computed_checksum != maybe_checksum:
            return False
        return True

    def listener(self):
        while not self.closed:
            try:
                data, addr = self.socket.recvfrom()

                if self.timer < time.time():
                    self.timer+=2.50
                    self.retransmit_unacknowledged_packets()
                    
                if len(data) >= 13:
                    if self.valid_checksum_checker(data):
                        seq_num_on_packet, ack_num_on_packet, flags, checksum = struct.unpack('!IIBI', data[:13])
                        data_bytes = data[13:]

                        is_ack = (flags & 0x1)
                        if is_ack:  # packet is acknowledgement
                            with self.lock:
                                if ack_num_on_packet in self.unacknowledged_packets:
                                    # ack num will be same as seq num
                                    self.unacknowledged_packets.pop(ack_num_on_packet)

                        is_fin = (flags & 0x2)
                        if is_fin: # packet is fin
                            self.fin = True
                            fin_ack_packet = struct.pack('!IIB', seq_num_on_packet, seq_num_on_packet, self.flag_byte_setter(is_fin_acknowledgement=True))
                            fin_ack_packet_with_checksum = self.packet_checksummer(fin_ack_packet)
                            self.socket.sendto(fin_ack_packet_with_checksum, (self.dst_ip, self.dst_port))

                        is_fin_ack = (flags & 0x4)
                        if is_fin_ack and self.fin: # packet is fin ACK
                            self.fin_ackd = True
                            self.ack_num += 1
                        
                        if not is_ack and not is_fin and not is_fin_ack:  # packet is data from client
                            with self.lock:
                                heappush(self.receive_buffer, (seq_num_on_packet, data_bytes)) # add to receive buffer
                        
                                self.unacknowledged_packets[seq_num_on_packet] = data # full packet (header+checksum+data)
                                
                            ack_packet = struct.pack('!IIB', seq_num_on_packet, seq_num_on_packet, self.flag_byte_setter(is_acknowledgement=True))
                            ack_packet_with_checksum = self.packet_checksummer(ack_packet)
                            self.socket.sendto(ack_packet_with_checksum, (self.dst_ip, self.dst_port))

                    
                    
                        # else:
                        #     ack_packet = struct.pack('!IIB', seq_num_on_packet, seq_num, self.flag_byte_setter(is_acknowledgement=True))
                        #     ack_packet_with_checksum = self.packet_checksummer(ack_packet)
                        #     self.socket.sendto(ack_packet_with_checksum, (self.dst_ip, self.dst_port))

                        # if addr[1] == 8001:  # sent FROM client
                        #     # with self.lock:
                        #     if seq_num_on_packet not in self.packet_dict and seq_num_on_packet <= self.listener_seq:
                        #         self.send_buffer.append(seq_num)


                        if addr[1] == 8000:  # sent TO client (ack)
                            # with self.lock:       
                            if ack_num_on_packet in self.send_buffer:
                                self.send_buffer.remove(ack_num_on_packet)
                        
                        
            except Exception as e:
                print("listener died!")
                print(e)

    def send(self, data_bytes: bytes) -> None:
        """Note that data_bytes can be larger than one packet."""
        """ Allow Streamer#send to support data larger than 1472 bytes.
        Break the data_bytes into chunks and send the data in multiple packets. """
        byte_size = len(data_bytes)
        max_seg_size = 1472 - 4 - 4 - 4 - 1  # 9 bytes for the sequence number, ack number, and flags
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
                header = struct.pack('!IIB', self.seq, self.ack_num, 0)  # seq, ack, flag
                full_packet = header + i
                full_packet_with_checksum = self.packet_checksummer(full_packet)

                self.unacknowledged_packets[self.seq] = full_packet_with_checksum
                heappush(self.send_buffer, (self.seq))
                # print(f"added {self.seq} to unack dictionary")
                self.socket.sendto(full_packet_with_checksum, (self.dst_ip, self.dst_port))
                self.seq += 1
        else:
            header = struct.pack('!IIB', self.seq, self.ack_num, 0)
            full_packet = header + data_bytes
            full_packet_with_checksum = self.packet_checksummer(full_packet)
            
            self.unacknowledged_packets[self.seq] = full_packet_with_checksum
            heappush(self.send_buffer, (self.seq))
            # print(f"added {self.seq} to unack dictionary")
            self.socket.sendto(full_packet_with_checksum, (self.dst_ip, self.dst_port))
            self.seq += 1
        

    def retransmit_unacknowledged_packets(self):
        with self.lock:
            print(f"unack dic:{self.unacknowledged_packets} send buff: {self.send_buffer}")
            if self.unacknowledged_packets and self.send_buffer: # seq : full_packet
                lowest_packet_to_resend = heappop(self.send_buffer)
                if lowest_packet_to_resend in self.unacknowledged_packets:
                    print(f"resending {lowest_packet_to_resend}")
                    self.socket.sendto(self.unacknowledged_packets[lowest_packet_to_resend], (self.dst_ip, self.dst_port))


    def recv(self) -> bytes:
        """Blocks (waits) if no data is ready to be read from the connection."""
        
        complete_data = bytes()
        while not (self.receive_buffer and self.receive_buffer[0][0] == self.expected_seq):
            time.sleep(0.01)

        with self.lock:
            while self.receive_buffer and self.receive_buffer[0][0] == self.expected_seq:
                seq_num, data_bytes = heappop(self.receive_buffer)
                self.expected_seq+=1
                print(f"now expecting {self.expected_seq}")
                if seq_num in self.unacknowledged_packets:
                    self.ack_num = seq_num
                    self.unacknowledged_packets.pop(seq_num)
                    print(f"now acknowledged, removed from dic: {seq_num}")
                if seq_num in self.send_buffer:
                    self.send_buffer.remove(seq_num)
            
                complete_data += data_bytes
             
                return complete_data

    def close(self) -> None:
        """Cleans up. It should block (wait) until the Streamer is done with all
           the necessary ACKs and retransmissions"""
        # with self.lock:
        while self.unacknowledged_packets:
            time.sleep(0.01)

        while True:
            fin_packet = struct.pack('!IIB', 0, 0, self.flag_byte_setter(is_fin_packet=True))
            fin_packet_with_checksum = self.packet_checksummer(fin_packet)
            self.socket.sendto(fin_packet_with_checksum, (self.dst_ip, self.dst_port))
            stalling = time.time() + 0.25
            
            while time.time() < stalling:
                if self.fin_ackd:
                    break
                time.sleep(0.01)

            if self.fin_ackd:
                break

        time.sleep(2)
        self.closed = True
        self.socket.stoprecv()