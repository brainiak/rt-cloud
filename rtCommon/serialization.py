import os
import hashlib
import logging
import numpy
import zlib
from base64 import b64encode, b64decode
from rtCommon.structDict import StructDict
from rtCommon.errors import RequestError, StateError, ValidationError

# Cache of multi-part data transfers in progress
multiPartDataCache = {}
dataPartSize = 10 * (2**20)


def encodeByteTypeArgs(cmd) -> dict:
    """
    Check if any args are of type 'bytes' and if so base64 encode them.
    The original arg will be replaced with a tag that will reference
    the encoded bytes within the cmd dict.
    Args:
        cmd: a dictionary of the command to check
    Returns:
        A cmd dictionary with the byte args encoded
    """
    args = cmd.get('args', ())
    byteArgIndices = []
    for i, arg in enumerate(args):
        if type(arg) is bytes:
            byteArgIndices.append(i)

    if len(byteArgIndices) != 0:
        # convert args from tuple to list so we can modify it
        args = list(args)
        for i in byteArgIndices:
            # encode as base64 and put a tag holder in place
            encdata = b64encode(args[i]).decode('utf-8')
            tag = 'encodedBytes_' + str(i)
            args[i] = tag
            cmd[tag] = encdata
        cmd['args'] = tuple(args)
        cmd['encodedByteArgs'] = byteArgIndices

    # Check and encode keyword args also
    kwargs = cmd.get('kwargs', {})
    byteKwargKeys = []
    for key, arg in kwargs.items():
        if type(arg) is bytes:
            byteKwargKeys.append(key)
            encdata = b64encode(arg).decode('utf-8')
            kwargs[key] = encdata
    if len(byteKwargKeys) != 0:
        cmd['encodedByteKwargs'] = byteKwargKeys
        cmd['kwargs'] = kwargs

    return cmd


def decodeByteTypeArgs(cmd) -> dict:
    """
    Decodes rpc args that were previously encoded with encodeByteTypeArgs.
    Args:
        cmd: a dictionary with encoded args
    Returns:
        cmd: a dictionary with decoded args
    """
    byteArgIndices = cmd.get('encodedByteArgs')
    if byteArgIndices is not None:
        args = cmd.get('args', ())
        args = list(args)
        for i in byteArgIndices:
            tag = 'encodedBytes_' + str(i)
            encdata = cmd.get(tag)
            if encdata is None or args[i] != tag:
                raise RequestError(f'Byte encoded data error: index {i} tag {tag}')
            decodedData = b64decode(encdata)
            args[i] = decodedData
            cmd.pop(tag, None)
        cmd.pop('encodedByteArgs')
        cmd['args'] = tuple(args)
    return cmd


def npToPy(data):
    """
    Converts components in data that are numpy types to regular python types.
    Uses recursive calls to convert nested data structures
    Returns:
        The data structure with numpy elements converted to python types
    """
    if isinstance(data, numpy.generic):
        return data.item()
    elif isinstance(data, dict):
        data2 = {key: npToPy(val) for key, val in data.items()}
        return data2
    elif isinstance(data, list):
        data2 = [npToPy(val) for val in data]
        return data2
    elif isinstance(data, tuple):
        data2 = [npToPy(val) for val in data]
        return tuple(data2)
    elif isinstance(data, set):
        data2 = [npToPy(val) for val in data]
        return set(data2)
    else:
        return data
    # Previous comprehensions, but they weren't recursive
    # args_list = [a.item() if isinstance(a, numpy.generic) else a for a in args]
    # args = tuple(args_list)
    # kwargs = {key: val.item() if isinstance(val, numpy.generic) else val for key, val in kwargs.items()}


def encodeMessageData(message, data, compress):
    """
    b64 encode binary data in preparation for sending. Updates the message header
    as needed
    Args:
        message (dict): message header
        data (bytes): binary data
        compress (bool): whether to compress binary data
    Returns:
        Modified message dict with appropriate fields filled in
    """
    message['hash'] = hashlib.md5(data).hexdigest()
    dataSize = len(data)
    if compress or dataSize > (20*2**20):
        message['compressed'] = True
        data = zlib.compress(data)
    message['data'] = b64encode(data).decode('utf-8')
    message['dataSize'] = dataSize
    # if 'compressed' in message:
    #     print('Compression ratio: {:.2f}'.format(len(message['data'])/dataSize))
    if len(message['data']) > 100*1024*1024:
        message['data'] = None
        raise ValidationError('encodeMessageData: encoded file exceeds max size of 100MB')
    return message


def decodeMessageData(message):
    """
    Given a message encoded with encodeMessageData (above), decode that message.
    Validate and retrive orignal bytes.
    Args:
        message (dict): encoded message to decode
    Returns:
        The byte data of the original message from the sender
    """
    data = None
    if 'data' not in message:
        raise RequestError('decodeMessageData: data field not in response')
    decodedData = b64decode(message['data'])
    if 'compressed' in message:
        data = zlib.decompress(decodedData)
    else:
        data = decodedData
    if 'hash' in message:
        dataHash = hashlib.md5(data).hexdigest()
        if dataHash != message['hash']:
            raise RequestError('decodeMessageData: Hash checksum mismatch {} {}'.
                               format(dataHash, message['hash']))
    return data


def generateDataParts(data, msg, compress):
    """
    A python "generator" that, for data > 10 MB, will create multi-part
    messages of 10MB each to send the data incrementally
    Args:
        data (bytes): data to send
        msg (dict): message header for the request
        compress (bool): whether to compress the data befor sending
    Returns:
        Repeated calls return the next partial message to be sent until
            None is returned
    """
    # TODO - for multipart assert type is bytes, or eventually support string type also
    dataSize = len(data)
    # will only multipart encode if the message is > dataPartSize (10MB)
    numParts = (dataSize + dataPartSize - 1) // dataPartSize
    # update message for all data parts with the following info
    msg['status'] = 200
    msg['fileSize'] = dataSize
    msg['fileHash'] = hashlib.md5(data).hexdigest()
    msg['numParts'] = numParts
    if numParts > 1:
        msg['multipart'] = True
    i = 0
    partId = 0
    dataSize = len(data)
    while i < dataSize:
        msgPart = msg.copy()
        partId += 1
        sendSize = dataSize - i
        if sendSize > dataPartSize:
            sendSize = dataPartSize
        dataPart = data[i:i+sendSize]
        msgPart['partId'] = partId
        try:
            msgPart = encodeMessageData(msgPart, dataPart, compress)
        except Exception as err:
            msgPart['status'] = 400
            msgPart['error'] = str(err)
            yield msgPart
            break
        yield msgPart
        i += sendSize
    return


def unpackDataMessage(msg):
    """
    Handles receiving multipart (an singlepart) data messages and returns the data bytes.
    In the case of multipart messages a data cache is used to store intermediate parts
    until all parts are received and the final data can be reconstructed.
    Args:
        msg (dict): Potentially on part of a multipart message to unpack
    Returns:
        None if not all multipart messages have been received yet, or
        Data bytes if all multipart messages have been received.
    """
    global multiPartDataCache
    try:
        if msg.get('status') != 200:
            # On error delete any partial transfers
            fileHash = msg.get('fileHash')
            if fileHash is not None and fileHash in multiPartDataCache:
                del multiPartDataCache[fileHash]
            raise RequestError('unpackDataMessage: {} {}'.format(msg.get('status'), msg.get('error')))
        data = decodeMessageData(msg)
        multipart = msg.get('multipart', False)
        numParts = msg.get('numParts', 1)
        partId = msg.get('partId', 1)
        logging.debug('unpackDataMessage: callid {}, part {} of {}'.format(msg.get('callId'), partId, numParts))
        if multipart is False or numParts == 1:
            # All data sent in a single message
            return data
        else:
            assert numParts > 1
            assert multipart is True
            if partId > numParts:
                raise RequestError(
                    'unpackDataMessage: Inconsistent parts: partId {} exceeds numParts {}'.
                    format(partId, numParts))
            # get the data structure for this data
            fileHash = msg.get('fileHash')
            if partId > 1:
                partialDataStruct = multiPartDataCache.get(fileHash)
                if partialDataStruct is None:
                    raise RequestError('unpackDataMessage: partialDataStruct not found')
            else:
                partialDataStruct = StructDict({'cachedDataParts': [None]*numParts, 'numCachedParts': 0})
                multiPartDataCache[fileHash] = partialDataStruct
            partialDataStruct.cachedDataParts[partId-1] = data
            partialDataStruct.numCachedParts += 1
            if partialDataStruct.numCachedParts == numParts:
                # All parts of the multipart transfer have been received
                # Concatenate the data into one bytearray
                data = bytearray()
                for i in range(numParts):
                    dataPart = partialDataStruct.cachedDataParts[i]
                    if dataPart is None:
                        raise StateError('unpackDataMessage: missing dataPart {}'.format(i))
                    data.extend(dataPart)
                # Check fileHash and fileSize
                dataHash = hashlib.md5(data).hexdigest()
                dataSize = len(data)
                if dataHash != fileHash:
                    raise RequestError("unpackDataMessage: File checksum mismatch {} {}".
                                       format(dataHash, fileHash))
                if dataSize != msg.get('fileSize', 0):
                    raise RequestError("unpackDataMessage: File size mismatch {} {}".
                                       format(dataSize, msg.get('fileSize', 0)))
                # delete the multipart data cache for this item
                del multiPartDataCache[fileHash]
                return data
        # Multi-part transfer not complete, nothing to return
        return None
    except Exception as err:
        # removed any cached data
        fileHash = msg.get('fileHash')
        if fileHash and fileHash in multiPartDataCache:
            del multiPartDataCache[fileHash]
        raise err
