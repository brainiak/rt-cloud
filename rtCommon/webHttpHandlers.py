"""
This module provides the callback handlers what the web server will utilize
    when handling and rendering html page reqeusts.
"""
import os
import time
import threading
import bcrypt
import logging
import tornado.web
from rtCommon.utils import DebugLevels

certsDir = 'certs'
maxDaysLoginCookieValid = 0.5

class HttpHandler(tornado.web.RequestHandler):
    """Generic web handler object that is initialized with the page name to render when called."""
    def initialize(self, webObject, page):
        self.web = webObject
        self.page = page
        self.httpLock = threading.Lock()

    def get_current_user(self):
        return self.get_secure_cookie("login", max_age_days=maxDaysLoginCookieValid)

    @tornado.web.authenticated
    def get(self):
        full_path = os.path.join(self.web.htmlDir, self.page)
        logging.log(DebugLevels.L6, f'{self.request.uri} request: pwd: {full_path}')
        self.httpLock.acquire()
        try:
            self.render(full_path)
        finally:
            self.httpLock.release()


class LoginHandler(tornado.web.RequestHandler):
    """Renders a login page and authenticates users. Sets a secure-cookie to remeber authenticated users."""
    loginAttempts = {}
    loginRetryDelay = 10

    def initialize(self, webObject):
        self.web = webObject

    def get(self):
        params = {
            "error_msg": '',
            "nextpage": self.get_argument("next", "/")
        }
        full_path = os.path.join(self.web.htmlDir, self.web.webLoginPage)
        self.render(full_path,  **params)

    def post(self):
        errorReply = None
        try:
            login_name = self.get_argument("name")
            login_passwd = self.get_argument("password")
            if self.web.testMode is True:
                if login_name == login_passwd == 'test':
                    self.set_secure_cookie("login", login_name, expires_days=maxDaysLoginCookieValid)
                    self.redirect(self.get_query_argument('next', '/'))
                    return
            passwdFilename = os.path.join(certsDir, 'passwd')
            passwdDict = loadPasswdFile(passwdFilename)
            if login_name in passwdDict:
                errorReply = self.checkRetry(login_name)
                if errorReply is None:
                    hashed_passwd = passwdDict[login_name]
                    # checkpw expects bytes array rather than string so use .encode()
                    if bcrypt.checkpw(login_passwd.encode(), hashed_passwd.encode()) is True:
                        # Remove failed attempts entry
                        del self.loginAttempts[login_name]
                        self.set_secure_cookie("login", login_name, expires_days=maxDaysLoginCookieValid)
                        self.redirect(self.get_query_argument('next', '/'))
                        return
                    else:
                        errorReply = 'Login Error: Login Incorrect'
            else:
                errorReply = self.checkRetry('invalid_user')
                if errorReply is None:
                    errorReply = 'Login Error: Login Incorrect'
        except Exception as err:
            errorReply = 'Exception: {} {}'.format(type(err), err)
        assert errorReply is not None, "Assert: LoginHandler.error not empty"
        logging.warning('Login Failure: {}'.format(login_name))
        params = {
            "error_msg": errorReply,
            "nextpage": self.get_query_argument('next', '/')
        }
        full_path = os.path.join(self.web.htmlDir, self.web.webLoginPage)
        self.render(full_path,  **params)

    def checkRetry(self, user):
        '''Keep a dictionary with one entry per username. Any user not in the
            passwd file will be entered as 'invalid_user'. Record login failure
            count and timestamp for when the next retry is allowed. Reset failed
            retry count on successful login. Return message with how many seconds
            until next login attempt is allowed.
        '''
        now = time.time()
        loginAttempts = self.loginAttempts
        retryTime = now + self.loginRetryDelay
        loginTry = loginAttempts.get(user)
        if loginTry is not None:
            failedLogins = loginTry.get('failedLogins', 0)
            nextAllowedTime = loginTry.get('nextAllowedTime', now)
            # print('user: {}, tries {}, nextTime {}'.format(user, failedLogins, nextAllowedTime))
            if nextAllowedTime > now:
                delaySecs = loginTry['nextAllowedTime'] - now
                return 'Next login retry allowed in {} sec'.format(int(delaySecs))
            loginTry['failedLogins'] = failedLogins + 1
            loginTry['nextAllowedTime'] = retryTime
            loginAttempts[user] = loginTry
        else:
            loginAttempts[user] = {'failedLogins': 1, 'nextAllowedTime': retryTime}
        return None

class LogoutHandler(tornado.web.RequestHandler):
    """Clears the secure-cookie so that users will need to re-authenticate."""
    def initialize(self, webObject):
        self.web = webObject

    def get(self):
        self.clear_cookie("login")
        self.redirect("/login")


def loadPasswdFile(filename):
    with open(filename, 'r') as fh:
        entries = fh.readlines()
    passwdDict = {k: v for (k, v) in [line.strip().split(',') for line in entries]}
    return passwdDict


def storePasswdFile(filename, passwdDict):
    with open(filename, 'w') as fh:
        for k, v in passwdDict.items():
            fh.write('{},{}\n'.format(k, v))