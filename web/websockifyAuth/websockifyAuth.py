import os
import tornado.web
import tornado.httputil
from websockify.auth_plugins import BasePlugin, AuthenticationError


class CookieAuth(BasePlugin):
    def authenticate(self, headers, target_host, target_port):
        raw_cookies = headers.get('Cookie')
        # fix up line so we can use httputil._parse_header()
        cookies_line = 'Cookies; ' + raw_cookies
        _, cookies = tornado.httputil._parse_header(cookies_line)
        if not 'login' in cookies:
            raise AuthenticationError('Missing login cookie', response_code=403)
        # get cookie secret
        if self.source is None:
            raise AuthenticationError('Use --auth-source <file> to specify cookie-secret file', response_code=403)
        if not os.path.exists(self.source):
            raise AuthenticationError('Cookie-secret file {} not found'.format(self.source), response_code=403)
        with open(self.source, mode='rb') as fh:
            cookieSecret = fh.read()
        value = tornado.web.decode_signed_value(cookieSecret, 'login', cookies['login'])
        if value is None:
            raise AuthenticationError('Invalid cookie', response_code=403)
        # TODO - log authenticated username which is the decoded value
        return
