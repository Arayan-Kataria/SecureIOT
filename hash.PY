import os
import hashlib
from pymongo import MongoClient
def add_user(username, password):
    client = MongoClient("mongodb://localhost:27017/")
    db = client.IOT
    #TODO:sanitize data
    #check to see if that username is already used
    if db.login_info.find_one({"username": username}) is None:
        #hash password
        # line.encode('utf-8')
        m = hashlib.sha256()
        #password.encode('utf-8')
        m.update(password)

        db.login_info.insert_one({"username": username, "password": m.hexdigest()})
    else:
        print ("Error: Username \""+username+"\" is already in use.")
user = input("username : ")
username = user.encode()
passW = input("password : ")
password = passW.encode()
add_user(username, password)