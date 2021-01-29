"""
A command-line script to add or change a user/password for access to the web portal.
The password file is store in rt-cloud/certs/passwd

Examples:
    $ python addLogin.py   # username and password will be requested at prompt
    $ python addLogin.py -u <username> -p <password>
    $ python addLogin.py -username <username> -password <password>
"""
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
from rtCommon.webHttpHandlers import loadPasswdFile, storePasswdFile

passwordFile = 'certs/passwd'


def addUserPassword(username, password, pwdFile, retypePasswd=True):
    if password is None:
        password = getpass.getpass('New Password:')
    if retypePasswd:
        password1 = getpass.getpass('Retype New Password:')
        if password != password1:
            print("Passwords don't match")
            sys.exit()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    passwdDict = loadPasswdFile(pwdFile)
    passwdDict[username] = hashed.decode()
    storePasswdFile(pwdFile, passwdDict)
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
            addUserPassword(username, password, passwordFile)
        else:
            print('Incorrect password')
            sys.exit()
    else:
        print("{} doesn't exist, adding as new user".format(username))
        addUserPassword(username, password, passwordFile)


if __name__ == "__main__":
    argParser = argparse.ArgumentParser()
    argParser.add_argument('--username', '-u', default=None, type=str)
    argParser.add_argument('--password', '-p', default=None, type=str)
    args = argParser.parse_args()
    main(args.username, args.password)
