"""Excpetion definitions for rtfMRI"""


class RTError(Exception):
    """Top level general error"""
    pass


class ValidationError(RTError):
    """Invalid information supplied in a call"""
    pass


class StateError(RTError):
    """System is not in a valid state relative to the request"""
    pass


class RequestError(RTError):
    """Error in the request"""
    pass


class MessageError(RTError):
    """Invalid message"""
    pass


class InvocationError(RTError):
    """program arguments incorrect"""
    pass


class VersionError(RTError):
    """Client/Server code versions don't agree"""
    pass


class MissedDeadlineError(RTError):
    """Server missed a deadline"""
    pass


class MissedMultipleDeadlines(RTError):
    """Server missed two or more deadlines"""
    pass

class NotImplementedError(RTError):
    """Functionality is not implemented yet"""
    pass
