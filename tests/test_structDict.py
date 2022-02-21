import os
import pytest  # type: ignore
import copy
import numpy as np  # type: ignore
import scipy.io as sio  # type: ignore
import rtCommon.utils as utils  # type: ignore
import rtCommon.validationUtils as vutils  # type: ignore
from rtCommon.structDict import StructDict, MatlabStructDict  # type: ignore
from rtCommon.structDict import recurseCreateStructDict, recurseSDtoDict


@pytest.fixture(scope="module")
def matTestFilename():  # type: ignore
    return os.path.join(os.path.dirname(__file__), 'test_input/teststruct.mat')


class TestMatlabStructDict:
    @pytest.fixture(scope="class")
    def testStruct(cls, matTestFilename):  # type: ignore
        print("## INIT TESTSTRUCT ##")
        teststruct0 = sio.loadmat(matTestFilename)
        testStruct = MatlabStructDict(teststruct0, 'test')
        return testStruct

    def test_loadStruct(self, testStruct):
        print("Test MatlabStructDict:")
        test = copy.deepcopy(testStruct)
        assert test.sub2 == 12
        assert test.top1 == 21
        assert test.top2 == 'hello'
        a = np.array([[[1, 13], [2, 14], [3, 15], [4, 16]],
                      [[5, 17], [6, 18], [7, 19], [8, 20]],
                      [[9, 21], [10, 22], [11, 23], [12, 24]]], dtype=np.uint8)
        assert np.array_equal(test.sub1, a)
        test.test.sub3 = np.array([1, 2, 3])
        assert test['test']['sub3'] is test.sub3
        assert np.array_equal(test.sub3, np.array([1, 2, 3]))
        test.top3 = np.array([[4, 5, 6], [7, 8, 9]])
        assert test['top3'] is test.top3
        assert np.array_equal(
            test.top3, np.array([[4, 5, 6], [7, 8, 9]]))
        test.sub3[0] = 3
        assert np.array_equal(test.sub3, np.array([3, 2, 3]))
        test.sub3 = np.array([10, 20, 30])
        assert np.array_equal(test.sub3, np.array([10, 20, 30]))
        fields = test.fields()
        expected_fields = set(
            ['sub1', 'sub2', 'sub3', 'top1', 'top2', 'top3', 'test'])
        assert fields == expected_fields

    def test_loadMatlabFile(self, testStruct, matTestFilename):
        print("Test LoadMatlabFile")
        struct2 = utils.loadMatFile(matTestFilename)
        assert testStruct.__name__ == struct2.__name__
        res = vutils.compareMatStructs(testStruct, struct2)
        assert vutils.isMeanWithinThreshold(res, 0)

        with open(matTestFilename, 'rb') as fp:
            data = fp.read()
        struct3 = utils.loadMatFileFromBuffer(data)
        res = vutils.compareMatStructs(testStruct, struct3)
        assert vutils.isMeanWithinThreshold(res, 0)

    def test_recurse(self):
        structDictType = type(StructDict())
        d1 = {'TR': [{'a': 1, 'b': {'c': 2}}]}

        sd1 = recurseCreateStructDict(d1)
        assert type(sd1) == structDictType
        assert type(sd1.TR[0]) == structDictType
        assert type(sd1.TR[0].b) == structDictType

        d2 = recurseSDtoDict(sd1)
        assert type(d2) == dict
        assert type(d2['TR'][0]) == dict
        assert type(d2['TR'][0]['b']) == dict
        assert d2 == d1



class TestStructDict:
    def test_structDict(self):
        print("Test StructDict:")
        a = StructDict()
        a.top = 1
        a.bottom = 3
        a.sub = StructDict()
        a.sub.left = 'corner'
        assert a.top == 1 and a.bottom == 3 and a.sub.left == 'corner'
