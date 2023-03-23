import hashlib, uuid
import os, sys, time, random
import messaging_util
from socket import *
from Crypto.PublicKey import RSA
from Crypto import Random
from Crypto.Cipher import PKCS1_OAEP
from base64 import b64decode
from pymongo import MongoClient
#DEFINES
DEVICE_NAME = "" #Name of the device running the script
BROADCAST_PORT = 50000 #The port used to broadcast device being alive
RECV_PORT = 50001 #Port used to exchange messages with the client
TIMEOUT = 60 #seconds #Timeout for socket recv/send
MAX_CACHE = 10 #Max entries in salt table
PUB_KEY_FILE = "IOTrsa.pub" #The file storing the public key of the IOT (4096bits)
PRIV_KEY_FILE = "IOTrsa" #The file storing the private key of the IOT (Never send anywhere)
REFRESH_TIMESTEP = 3600 #Amount of time it takes before block list is refr

block_list = None
table = None
sock = None
broadcast = None
secret_num = 0
seq_num = 0
#END DEFINES
'''
initialize the global variables such as public/private key info
'''
def init():
    global user #username of current user
    global table #keeps track of salt used for message, helps for delayed responses
    global pubkey #Object form of IOT's public key
    global privkey #Object form of IOT's private key
    global pubtext #Text form of IOT's public key
    global client_pub #public key of the client in object form
    global client_pub_text #textual version of the client's pub key
    global sock #UDP socket used for normal connection
    global broadcast #UDP socket used to broadcast
    global user_logged_in #Flag used to track if a user is currently connected to this IOT
    global block_list #List of (IP, port) tuples to block
    global DEVICE_NAME
    DEVICE_NAME = gethostname()
    user = None
    user_logged_in = False
    block_list = list()
    broadcast = socket(AF_INET, SOCK_DGRAM)
    broadcast.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    broadcast.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.bind(('', RECV_PORT))
    sock.settimeout(TIMEOUT)
    table = dict()
    #Initialize global public key for IOT
    pub = open(PUB_KEY_FILE, "r");
    pubtext = pub.read()
    
    pubkey = RSA.importKey(pubtext)
    pubkey = PKCS1_OAEP.new(pubkey)
    pub.close()
    #Initialize global private key for IOT
    priv = open(PRIV_KEY_FILE, "r")
    privtext = priv.read()
    privkey = RSA.importKey(privtext)
    privkey = PKCS1_OAEP.new(privkey)
    priv.close()
'''
This is a method to encrypt a message using a 4096 bit RSA encryption with
OAEP padding.
It uses the public key of the recipient to encrypt the message. The reciever
uses their private key to decrypt the message. This is Asymmetric encryption.
@para: public_key Public key object
@param message String to be encrypted
@return base64 encoded encrypted string
'''
def encrypt_RSA(public_key, message):
    pub = public_key
    encrypted = pub.encrypt(message)
    return encrypted.encode('base64')
'''
This is the method to decrypt using 4096 but RSA encryption with PKCS1_OAEP
padding.
It uses this IOT's private key to decrypt the 'package' and return the base64
decoded decrypted string.
@param package String to be decrypted
@returns decrypted string
'''
def decrypt_RSA(package):
    key = open(PRIV_KEY_FILE, "r").read()
    rsakey = RSA.importKey(key)
    rsakey = PKCS1_OAEP.new(rsakey)
    decrypted = rsakey.decrypt(b64decode(package))
    return decrypted
'''
Wrapper for sending message, with try catch for timeout error
@param s socket to send stuff through
@param msg message to send through socket
@param addr destination of message
'''

def send(s, msg, addr):
    sent = False
    while sent == False:
        try:
            num_sent = s.sendto(msg, addr)
            sent = True
        except timeout: #socket.error is subclass
            print ("No network connection, trying again later...")
            time.sleep(60) #check back in a minute
'''
adds salt to table, in LRU scheme
@param num number that correspends to the salt
@param salt salt to hash passwords with
'''
def cache_salt(num, salt):
    global table
    num = int(num)
    #check if the table is full
    if len(table) == MAX_CACHE :
    #remove the least recently used key
        lru = min(table.keys())
        del table[lru]
        table[num] = salt
    '''
    takes UDP socket as input, broadcasts salt to be used in encryption
    @param s socket to broadcast through
    @param num salt number - used later to find the salt to verify password
    @return salt generated by this connect message
    '''
def brocast(s, num):
    msg = "CONNECT:"
    salt = str(uuid.uuid4().hex)
    msg += salt
    msg += ","
    msg += str(num)
    msg += ","
    msg += DEVICE_NAME
    print (msg)
    send(s, msg, ('<broadcast>', BROADCAST_PORT))
    return salt

def login(username, password, salt, new_salt, addr):
    global user_logged_in
    global user
    global secret_num
    if check_password(username, password, salt) is False:
    #user not found
        send(sock, "ERROR:LOGIN", addr)
        return False
    #login successful
    user = username
    #re-hash password to ensure Encrypt ack is authentic
    newhash = hash_password(new_salt)
    #do diffie stuff
    secret_num, diffyH = messaging_util.get_diffie_nums()
    send(sock, "ACK:ENCRYPT,"+ pubtext + "," + newhash + "," + diffyH, addr)
    return True

def hash_password(salt):
    if user is None:
        return None
    client = MongoClient()
    db = client.IOT.login_info
    entry = db.find_one({"username": user})
    print ("ENTRY > > > ", entry)
    if entry is None:
        return None
    return hashlib.sha256(entry["password"].encode() + \
    salt.encode()).hexdigest()
    
'''
searches table for salt
@param num index of the salt
@return salt at index num
'''
def get_salt(num):
    num = int(num)
    salt = table.get(num, None)
    return salt

def check_password(username, password, salt):
    #connect to mongodb
    client = MongoClient()
    db = client.IOT.login_info
    entry = db.find_one({"username" : username})
    if entry is None: #username dont match
        return False
    pwd = entry["password"]
    pwd = (hashlib.sha256(pwd.encode() + salt.encode())).hexdigest()
    return pwd == password


def ack(cmd, addr):
    global user_logged_in
    global client_pub_text
    global client_pub
    global seq_num
    ret = False
    c = cmd[1]
    if c == "PASS":
        if len(cmd) != 8:
            return False
        salt = get_salt(cmd[2])
        if salt == None:
            return False
        ret = login(cmd[3], cmd[4], salt, cmd[5], addr)
        if ret is False:
            return False
    #set seq. num from the diffie numbers
        seq_num = messaging_util.set_seq_num(secret_num, cmd[6])
        if seq_num is None:
            return False
#get client's public key information
        cpub = cmd[7]
        client_pub_text = cpub
        client_pub = RSA.importKey(cpub)
        client_pub = PKCS1_OAEP.new(client_pub)
        user_logged_in = addr
        ret = True
    else:
        send(s, "ERROR:ARGUMENT", addr)
    return ret

def send_secure(s, msg, addr):
    encrypted_msg = encrypt_RSA(client_pub,msg)
    send(s, encrypted_msg, addr)
    print ("Encrypted Message: \n"+encrypted_msg)
    
def handle_data(s, addr, msg):
    global send_brocast, user_logged_in, seq_num, user
    #Decrypt the msg and parse out the command field
    payload = decrypt_RSA(msg)
    payload = payload.split(":",1)
    #Command used by the client to end the connection with the IOT
    if(payload[0] == "FIN"):
    #check sequence number
        if seq_num != int(payload[1]):
            return
        print ("FIN command received, exiting!")
        #start sending brocasts again - now i'm available ;)
        send_brocast = True
        #no user lodged in anymore
        user_logged_in = False
        user = None
        return
    #invalid command
    elif (payload[0] != "DATA"):
        return
#Otherwise the command was DATA
    payload = payload[1]
    arr = payload.rsplit(",",1)
    #if insufficent # arguments, return
    if (len(arr) < 2):
        return
    #if seq. no. dont match, return
    if seq_num != int(arr[1]):
        return
    payload = arr[0] + "," + str(seq_num+1)
    #update to expected seq number
    seq_num = seq_num + 2
    payload = "You sent IOT: "+payload
    print ("Decrypted Payload: \n"+payload)
    #Securely send back the slightly modified message
    send_secure(s, payload, addr)
    
init()
msgCount = 0
send_brocast = True
refresh_list_time = time.time()
while 1:
    print ("");
    #print block_list
    if(time.time() >= refresh_list_time):
        del block_list[:]
        refresh_list_time = time.time() + REFRESH_TIMESTEP
        #increment salt#
    msgCount += 1
        #send brocast if need to
    if send_brocast == True:
        salt = brocast(broadcast, msgCount)
        cache_salt(msgCount, salt)
        
    recv = False
    try:
        msg, server = sock.recvfrom(8192)
        recv = True
        #print "message is " + str(msg) + "\nFrom " + str(server)
    except timeout:
        print ("Socket timeout, trying again!")
        continue
    #if no message, just continue loop
    if recv == False:
        continue
    #if the sender is blocked, just continue loop
    if server in block_list:
        continue
    #If a connection has been established already, handle data securely
    if(user_logged_in):
    #if the message is from a client != connected client, ignore message
        if(user_logged_in != server):
            send(s, "Bitch, I'm already connected.", server)
            block_list.append(server)
            continue
    #handle the encrypted message
        handle_data(sock, server, msg)
    #Otherwise, data does not have to be encrypted (and shouldn't be)
    else:
        cmd = messaging_util.parse_message(msg)
        if cmd == None: #bad formatting, blocking
            block_list.append(server)
            continue
        if cmd[0] == "ACK":
            success = ack(cmd, server)
            if success:
                send_brocast = False
        #break
print("Closing socket")
sock.close()