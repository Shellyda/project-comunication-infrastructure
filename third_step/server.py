import socket as skt
from threading import Thread
import env_props as env
from rdt_sender import RDT_Sender

# Constants from the environment configuration
MAX_BUFF_SIZE = env.MAX_BUFF_SIZE
bind_address = env.SERVER_ADDRESS

class Server:
    def __init__(self, socket_family=skt.AF_INET, socket_type=skt.SOCK_DGRAM, socket_binding=bind_address):
        # Initialize the server socket with the specified socket family and type (UDP in this case)
        self.server_socket = skt.socket(socket_family, socket_type)
        self.server_socket.bind(socket_binding)  # Binding the socket to the specified address and port
        self.clients = {}  # {username: (address, port)}
        self.accommodations = {}  # {(name, location): {'id': id, 'owner': (username, addr), 'available_days': [days], 'reservations': {day: (username, addr)}}}
        self.reservations = {}  # {(owner, id, day): (guest_name, guest_addr, location, name)}
        # List of available days for booking
        self.available_days = ["17/07/2024", "18/07/2024", "19/07/2024", "20/07/2024", "21/07/2024", "22/07/2024"]

    def handle_client(self, data, addr):
        # Decode the received data and split into command and arguments
        command = data.decode().split()
        action = command[0]
        
        # Handle different actions based on the command
        if action == "login":
            self.login(command[1], addr)
        elif action == "logout":
            self.logout(addr)
        elif action == "create":
            self.create_accommodation(command[1], command[2], addr)
        elif action == "list:myacmd":
            self.list_my_accommodations(addr)
        elif action == "list:acmd":
            self.list_accommodations(addr)
        elif action == "list:myrsv":
            self.list_my_reservations(addr)
        elif action == "book":
            self.book_accommodation(command[1], command[2], command[3], addr)
        elif action == "cancel":
            self.cancel_reservation(command[1], command[2], command[3], addr)
        elif action == "--help":
            self.show_help(addr)

    def login(self, username, addr):
        # Handle the login request
        if username in self.clients:
            self.send_data("Username already in use.".encode(), addr)
        else:
            self.clients[username] = addr
            self.send_data(f"Login successful {username}".encode(), addr)
            print('\x1b[1;37;93m' + f'User [{username}/{addr[0]}:{addr[1]}] is connected!' + '\x1b[37m')
    
    def logout(self, addr):
        # Handle the logout request
        username = self.get_username_by_address(addr)
        if username in self.clients:
            del self.clients[username]
            print('\x1b[1;31;40m' + f'User [{username}/{addr[0]}:{addr[1]}] disconnected!' + '\x1b[37m')

    def create_accommodation(self, name, location, addr):
        # Handle the request to create a new accommodation
        if (name, location) in self.accommodations:
            self.send_data("Accommodation already exists.".encode(), addr)
        else:
            # Generate a new accommodation ID and add it to the dictionary
            accommodation_id = len(self.accommodations) + 1
            self.accommodations[(name, location)] = {
                'id': accommodation_id,
                'owner': addr,
                'available_days': self.available_days.copy(),
                'reservations': {}
            }
            owner_name = self.get_username_by_address(addr)
            self.send_data(f"Accommodation {name} created successfully!".encode(), addr)
            # Notify all clients about the new accommodation, except the creator
            self.notify_all_clients(f"[{owner_name}/{addr[0]}:{addr[1]}] New accommodation {name} in {location} created!", exclude=addr)
    
    def list_my_accommodations(self, addr):
        # List all accommodations created by the user
        my_acmds = []
        for (name, location), details in self.accommodations.items():
            if details['owner'] == addr:
                res = details['reservations']
                # Format the accommodation information including available and reserved days
                acmd_info = f"ID {details['id']}: {name} in {location} \n- Available: {details['available_days']}\n - Reserved: {[(d, self.get_username_by_address(u)) for d, u in res.items()]}"
                my_acmds.append(acmd_info)
        # Send the formatted list to the user
        response = "\n".join(my_acmds) if my_acmds else "You have no accommodations."
        self.send_data(response.encode(), addr)
    
    def list_accommodations(self, addr):
        # List all available accommodations
        acmds = []
        for (name, location), details in self.accommodations.items():
            owner_name = self.get_username_by_address(details['owner'])
            # Format the accommodation information including available days and owner name
            acmd_info = f"ID {details['id']}: {name} in {location} - Available: {details['available_days']} - Owner: {owner_name}"
            acmds.append(acmd_info)
        # Send the formatted list to the user
        response = "\n".join(acmds) if acmds else "No accommodations available."
        self.send_data(response.encode(), addr)
    
    def list_my_reservations(self, addr):
        # List all reservations made by the user
        my_rsvs = []
        for (owner, id, day), (guest_name, guest_addr, location, name) in self.reservations.items():
            if guest_addr == addr:
                owner_name = self.get_username_by_address(owner)
                # Format the reservation information
                my_rsvs.append(f"[{owner_name}/{owner[0]}:{owner[1]}] Reservation: Accommodation ID {id}, {name} on {day} at {location}")
        # Send the formatted list to the user
        response = "\n".join(my_rsvs) if my_rsvs else "You have no reservations."
        self.send_data(response.encode(), addr)
    
    def book_accommodation(self, owner_name, acmd_id, day, addr):
        # Handle the request to book an accommodation
        owner_addr = self.get_addr_by_username(owner_name)
        if owner_addr and (owner_addr, acmd_id, day) in self.reservations:
            self.send_data("Accommodation already booked for this day.".encode(), addr)
        elif owner_addr == addr:
            self.send_data("You cannot reserve your own accommodation.".encode(), addr)
        else:
            if (owner_addr, acmd_id, day) not in self.reservations:
                for (name, location), details in self.accommodations.items():
                    if details['id'] == int(acmd_id) and day in details['available_days']:
                        # Update the accommodation's available days and reservations
                        details['available_days'].remove(day)
                        details['reservations'][day] = addr
                        self.reservations[(owner_addr, acmd_id, day)] = (self.get_username_by_address(addr), addr, location, name)
                        self.send_data(f"Booking successful for {name} on {day}.".encode(), addr)
                        self.notify_owner(owner_addr, f"[{self.get_username_by_address(addr)}/{addr[0]}:{addr[1]}] Reservation for {name} on {day}", subject="reservation")
                        return
            self.send_data("Accommodation or day unavailable.".encode(), addr)
    
    def cancel_reservation(self, owner_name, acmd_id, day, addr):
        # Handle the request to cancel a reservation
        owner_addr = self.get_addr_by_username(owner_name)
        if owner_addr and (owner_addr, acmd_id, day) in self.reservations and self.reservations[(owner_addr, acmd_id, day)][1] == addr:
            del self.reservations[(owner_addr, acmd_id, day)]
            for (name, location), details in self.accommodations.items():
                if details['id'] == int(acmd_id):
                    # Update the accommodation's available days and reservations
                    details['available_days'].append(day)
                    del details['reservations'][day]
                    self.send_data("Reservation cancelled successfully.".encode(), addr)
                    self.notify_owner(owner_addr, f"[{self.get_username_by_address(addr)}/{addr[0]}:{addr[1]}] Cancellation for {name} on {day}", subject="cancellation")
                    self.notify_all_clients(f"[{self.get_username_by_address(owner_addr)}/{owner_addr[0]}:{owner_addr[1]}] New availability for {name} in {location} on {day}", exclude=owner_addr)
                    return
        self.send_data("Reservation not found.".encode(), addr)
    
    def notify_all_clients(self, message, exclude=None):
        # Notify all clients with the specified message, excluding a particular address if provided
        for client_addr in self.clients.values():
            if client_addr != exclude:
                self.send_data(message.encode(), client_addr)
    
    def notify_owner(self, owner_addr, message, subject):
        # Notify the owner with the specified message
        if owner_addr:
            self.send_data(message.encode(), owner_addr)
    
    def show_help(self, addr):
        # Send a help message with the list of available commands
        help_message = """
Available commands:
- login <username>: Log in with a username
- logout: Log out
- create <name> <location>: Create a new accommodation
- list:myacmd: List your accommodations
- list:acmd: List all available accommodations
- list:myrsv: List your reservations
- book <owner> <id> <day>: Book an accommodation
- cancel <owner> <id> <day>: Cancel a reservation
- --help: Display this help message
"""
        self.send_data(help_message.encode(), addr)
    
    def get_username_by_address(self, addr):
        # Get the username corresponding to the specified address
        for username, client_addr in self.clients.items():
            if client_addr == addr:
                return username
        return None

    def get_addr_by_username(self, username):
        # Get the address corresponding to the specified username
        return self.clients.get(username, None)
            
    def send_data(self, data, target_address):
        # Send data using the reliable data transfer protocol
        sender = RDT_Sender(target_address)  
        sender.send(data)  # Use send method from RDT_Sender

    def run(self):
        print('\x1b[1;37;40m' + "Accommodation server started. Waiting for connections..." + '\x1b[37m')
        while True:
            # Receive data from the socket
            data, target_address = self.server_socket.recvfrom(MAX_BUFF_SIZE)
            # Handle each client request in a new thread
            Thread(target=self.handle_client, args=(data, target_address)).start()

if __name__ == "__main__":
    # Instantiate and run the server
    server = Server()
    server.run()
