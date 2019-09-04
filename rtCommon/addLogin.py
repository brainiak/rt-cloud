import os
import sys
import getpass
import bcrypt
import argparse
# import project modules
# Add base project path (two directories up)
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(currPath)
sys.path.append(rootPath)
from rtCommon.projectInterface import loadPasswdFile, storePasswdFile

passwordFile = 'certs/passwd'


def addUserPassword(username, password, passwdDict):
    if password is None:
        password = getpass.getpass('New Password:')
    password1 = getpass.getpass('Retype New Password:')
    if password != password1:
        print("Passwords don't match")
        sys.exit()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    passwdDict[username] = hashed.decode()
    storePasswdFile(passwordFile, passwdDict)
    print('password updated')
    return


def main(username, password):
    passwdDict = loadPasswdFile(passwordFile)
    if username is None:
        username = input('Username: ')
    if username in passwdDict:
        print('Changing password for {}'.format(username))
        old_password = getpass.getpass('Old Password:')
        hashed_passwd = passwdDict[username]
        if bcrypt.checkpw(old_password.encode(), hashed_passwd.encode()) is True:
            addUserPassword(username, password, passwdDict)
        else:
            print('Incorrect password')
            sys.exit()
    else:
        print("{} doesn't exist, adding as new user".format(username))
        addUserPassword(username, password, passwdDict)


if __name__ == "__main__":
    argParser = argparse.ArgumentParser()
    argParser.add_argument('--username', '-u', default=None, type=str)
    argParser.add_argument('--password', '-p', default=None, type=str)
    args = argParser.parse_args()
    main(args.username, args.password)
