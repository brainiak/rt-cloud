import pytest
from rtCommon.wsRemoteService import encodeByteTypeArgs, decodeByteTypeArgs


class TestRemoteable:
    def setup_class(cls):
        pass

    def teardown_class(cls):
        pass

    def test_encodeByteTypeArgs(self):
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



