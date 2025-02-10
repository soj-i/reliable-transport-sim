# do not import anything else from loss_socket besides LossyUDP
from lossy_socket import LossyUDP
# do not import anything else from socket except INADDR_ANY
from socket import INADDR_ANY


class Streamer:
    def __init__(self, dst_ip, dst_port,
                 src_ip=INADDR_ANY, src_port=0):
        """Default values listen on all network interfaces, chooses a random source port,
           and does not introduce any simulated packet loss."""
        self.socket = LossyUDP()
        self.socket.bind((src_ip, src_port))
        self.dst_ip = dst_ip
        self.dst_port = dst_port

    def send(self, data_bytes: bytes) -> None:
        """Note that data_bytes can be larger than one packet."""
        """ Allow Streamer#send to support data larger than 1472 bytes.
        Break the data_bytes into chunks and send the data in multiple packets. """
        # Your code goes here!  The code below should be changed!

        byte_size = len(data_bytes)
 
        splits = byte_size // 1472 # 23 / 4 -> 5 
        # (23) -> (0-3) (4-7) (8-11) (12-15) (16-19) (20-22)
        #         [0:4] [4:8] [8:12]  [12:16] [16:20] [20:23]
        start = 0
        byte_arr = [] # 4 |
        max_seg_size = 1472

        if byte_size > max_seg_size:
            for _ in range(splits):          
                end = start + max_seg_size # 4 8 12 16 20
                byte_arr.append(data_bytes[start:end])
                start = end

            if end < byte_size:
                byte_arr.append(data_bytes[end:byte_size])
        
            for i in byte_arr:
                self.socket.sendto(i,(self.dst_ip, self.dst_port) )
        else:
        # for now I'm just sending the raw application-level data in one UDP payload
            self.socket.sendto(data_bytes, (self.dst_ip, self.dst_port))

    def recv(self) -> bytes:
        """Blocks (waits) if no data is ready to be read from the connection."""
        # your code goes here!  The code below should be changed!
        
        # this sample code just calls the recvfrom method on the LossySocket
        data, addr = self.socket.recvfrom()
        # For now, I'll just pass the full UDP payload to the app
        return data

    def close(self) -> None:
        """Cleans up. It should block (wait) until the Streamer is done with all
           the necessary ACKs and retransmissions"""
        # your code goes here, especially after you add ACKs and retransmissions.
        pass
