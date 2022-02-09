import os
import pytest
import numpy
from rtCommon.errors import ValidationError
from rtCommon.serialization import npToPy
from rtCommon.serialization import encodeByteTypeArgs, decodeByteTypeArgs
from rtCommon.serialization import encodeMessageData, decodeMessageData
from rtCommon.serialization import generateDataParts, unpackDataMessage

def test_encodeByteTypeArgs():
    cmd = {'cmd': 'rpc', 'class': 'list', 'attribute': 'append',
            'args': ('orange', b'somebytes', 'grape', b'morebytes'),
            'kwargs': {'a': 23, 'b': b'optionalbytes'}}
    # Encode the command
    encoded_cmd = encodeByteTypeArgs(cmd)

    # check the encoded args
    encodedIndices = encoded_cmd.get('encodedByteArgs')
    assert encodedIndices is not None
    assert len(encodedIndices) == 2
    args = encoded_cmd.get('args', ())
    for i in encodedIndices:
        tag = 'encodedBytes_' + str(i)
        assert type(encoded_cmd.get(tag)) is str
        assert args[i] == tag

    # check the encoded kwargs
    kwargKeys = cmd.get('encodedByteKwargs')
    assert kwargKeys is not None
    assert len(kwargKeys) == 1
    kwargs = encoded_cmd.get('kwargs', ())
    for k in kwargKeys:
        assert type(kwargs[k]) is str

    # Decode the command
    decoded_cmd = decodeByteTypeArgs(encoded_cmd)
    assert cmd == decoded_cmd


def test_npToPy():
    data1 = {'subject': '04', 'task': 'story', 'suffix': 'bold', 'datatype': 'func', 'run': 1}
    data2 = {'a1': (1, 'two', 3.0),
                'a2': {'np': numpy.float32(3), 'pyint': 4, 'str': 'five'},
                'a3': [6.0, 'seven', numpy.int(8), {'a', numpy.float32(5), 'c'}]}
    data2_py = {'a1': (1, 'two', 3.0),
                'a2': {'np': 3.0, 'pyint': 4, 'str': 'five'},
                'a3': [6.0, 'seven', 8.0, {'a', 5.0, 'c'}]}
    kwargs = {'mdata': data2, 'test1': 9.0, 'test2': numpy.float32(9), 'test3': 'yes'}
    kwargs_py = {'mdata': data2_py, 'test1': 9.0, 'test2': 9.0, 'test3': 'yes'}
    args = (4, 'hello', data1, kwargs)
    args_py = (4, 'hello', data1, kwargs_py)
    res = npToPy(args)
    assert res == args_py


def test_encodeMessageData(bigTestFile, mediumTestFile):
    # Test medium sized data
    msg = {'test': 'mediumSize'}
    with open(mediumTestFile, 'rb') as fp:
        mediumData = fp.read()
    resMsg = encodeMessageData(msg, mediumData, compress=False)
    assert resMsg.get('compressed') == None
    resData = decodeMessageData(resMsg)
    assert resData == mediumData

    # Test data > 20 MB, should override to compress
    msg = {'test': 'largeSize'}
    largeData = bytes(os.urandom(21*2**20))
    # Should override and compress very large files
    resMsg = encodeMessageData(msg, largeData, compress=False)
    assert resMsg['compressed'] == True
    resData = decodeMessageData(resMsg)
    assert resData == largeData

    # Test compress flag
    bytesArg = b'1234'
    msg = {'test': 'compressFlag'}
    resMsg = encodeMessageData(msg, bytesArg, compress=True)
    assert resMsg['compressed'] == True
    resData = decodeMessageData(resMsg)
    assert resData == bytesArg

    # Test too big file - past max allowed size
    msg = {'test': 'tooBigSize'}
    with open(bigTestFile, 'rb') as fp:
        bigData = fp.read()
    with pytest.raises(ValidationError) as err:
        resMsg = encodeMessageData(msg, bigData, compress=False)


def test_generateDataParts(bigTestFile, mediumTestFile):
    # Test running two data decodings in parallel
    # Read in the data files
    medMsg = {'test': 'mediumSize'}
    with open(mediumTestFile, 'rb') as fp:
        mediumData = fp.read()
    bigMsg = {'test': 'bigSize'}
    with open(bigTestFile, 'rb') as fp:
        bigData = fp.read()
    medGen = generateDataParts(mediumData, medMsg, compress=True)
    bigGen = generateDataParts(bigData, bigMsg, compress=True)

    medParts = 0
    bigParts = 0
    for msgPart in bigGen:
        resBigData = unpackDataMessage(msgPart)
        bigParts += 1
        try:
            medMsgPart = next(medGen)
            medParts += 1
            resMediumData = unpackDataMessage(medMsgPart)
        except StopIteration:
            # no more message parts for medium sized data
            pass
    assert medParts > 1
    assert bigParts > 1
    assert resMediumData == mediumData
    assert resBigData == bigData
