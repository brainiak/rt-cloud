import os
import sys
import getpass
import bcrypt
# import project modules
# Add base project path (two directories up)
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(currPath)
sys.path.append(rootPath)
from web.webServer import loadPasswdFile, storePasswdFile

passwordFile = 'certs/passwd'


def addUserPassword(username, passwdDict):
    password = getpass.getpass('New Password:')
    password1 = getpass.getpass('Retype Password:')
    if password != password1:
        print("Passwords don't match")
        sys.exit()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    passwdDict[username] = hashed.decode()
    storePasswdFile(passwordFile, passwdDict)
    print('password updated')
    return


# Main Function
passwdDict = loadPasswdFile(passwordFile)
username = input('Username: ')
if username in passwdDict:
    print('Changing password for {}'.format(username))
    password = getpass.getpass('Old Password:')
    hashed_passwd = passwdDict[username]
    if bcrypt.checkpw(password.encode(), hashed_passwd.encode()) is True:
        addUserPassword(username, passwdDict)
    else:
        print('Incorrect password')
        sys.exit()
else:
    print("{} doesn't exist, adding as new user".format(username))
    addUserPassword(username, passwdDict)
