import socket as skt
import struct
from random import *
import env_props as env # Environment properties

MAX_BUFF_SIZE = env.MAX_BUFF_SIZE - 4  # 1024 - sequence_number = 1024 - sizeof(int)
TIMEOUT = 1.0 # 1000ms

class RDT_Sender:
   def __init__(self, target_address):
        self.socket = skt.socket(skt.AF_INET, skt.SOCK_DGRAM)
        self.socket.settimeout(TIMEOUT)
        self.target_address = target_address
        self.state = ""

   def send_packet(self, payload, sequence_number): # Converts the data into a string representation and encodes it into bytes
        packet_length = len(payload)
        data = bytearray(4 + packet_length)
        data = struct.pack(f'i {packet_length}s', sequence_number, payload)
        if randint(0, 3):   # 25% loss rate
            self.socket.sendto(data, self.target_address) # Sends the data to the destination

   def waiting_for_acknowledgement(self, sequence_number):
        # State of waiting for Ack, after packet has been sent
                try:
                    acknowledgement_packet = self.socket.recv(MAX_BUFF_SIZE) # If an Ack packet arrives, receives the Ack
                except skt.timeout:
                    self.action = f"resend_packet_seq_{sequence_number}" # If a timeout occurs, resend sequence packet 
                else:
                    acknowledgement_packet = struct.unpack_from('i', acknowledgement_packet) # Decodes the ACK packet
                    ack = acknowledgement_packet[0]             # Gets the ACK field of the packet
                    if ack == int(sequence_number):
                        self.action = f"stop_timer_{sequence_number}" # If the ACK is sequence_number, reset the timer
                        self.end_of_packet = True # If Received expected ACK
                        self.socket.sendto(b'END', self.target_address)
                    else:
                        self.action = f"resend_packet_seq_{sequence_number}" # If the ack has the wrong sequence, resend packet 

   def waiting_for_call(self, sequence_number):
        self.action = f"send_packet_seq_{sequence_number}" # Send sequence packet 

   def send_packet_sequence(self, sequence_number, data):
        self.send_packet(data, int(sequence_number))
        self.state = f"wait_ack_{sequence_number}"

   def stop_timer(self, sequence_number):
        self.socket.settimeout(TIMEOUT) # Reset timer

        if sequence_number == '0':
            new_call_sequence_number = '1' 
        else: 
            new_call_sequence_number = '0'

        self.state = f"wait_call_{new_call_sequence_number}" 
        

   def send(self, message):
        self.end_of_packet = False

        self.send_packet(message, 0)

        self.state = "wait_ack_0"

        while not self.end_of_packet: # Main loop of the sender's finite state machine
            # Waiting calls
            if self.state == "wait_call_0":
                # State of waiting to send sequence packet 0
                self.waiting_for_call('0')
            elif self.state == "wait_call_1":
                # State of waiting to send sequence packet 1
                self.waiting_for_call('1')
            elif self.state == "wait_ack_0":
                # State of waiting for Ack 0 after packet 0 has been sent
                self.waiting_for_acknowledgement('0')
            elif self.state == "wait_ack_1":
                # State of waiting for Ack 1 after packet 1 has been sent
                self.waiting_for_acknowledgement('1')

            # Packets sequences senders
            if self.action == "send_packet_seq_0" or self.action == "resend_packet_seq_0":
               self.send_packet_sequence('0', message)
            elif self.action == "send_packet_seq_1" or self.action == "resend_packet_seq_1":
               self.send_packet_sequence('1', message)

            # Stop timer
            elif self.action == "stop_timer_0":
                self.stop_timer('0')
            elif self.action == "stop_timer_1":
                self.stop_timer('1')