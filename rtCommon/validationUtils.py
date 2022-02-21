"""
ValidationUtils - utils to help validate that arrays and data structures match.
For example in testing and comparing to a known-good run from matlab.
"""

import numbers
import numpy as np  # type: ignore
import scipy.stats as sstats  # type: ignore
from .structDict import MatlabStructDict
from .utils import loadMatFile, flatten_1Ds

# Globals
numpyAllNumCodes = np.typecodes['AllFloat'] + \
    np.typecodes['AllInteger'] + np.typecodes['UnsignedInteger']
StatsEqual = {'mean': 0, 'count': 1, 'min': 0, 'max': 0, 'stddev': 0,
              'histocounts': None, 'histobins': None, 'histopct': None}
StatsNotEqual = {'mean': 1, 'count': 1, 'min': 1, 'max': 1, 'stddev': 1,
                 'histocounts': None, 'histobins': None, 'histopct': None}


def compareArrays(A: np.ndarray, B: np.ndarray) -> dict:
    """Compute element-wise percent difference between A and B
       Return the mean, max, stddev, histocounts, histobins in a Dict
    """
    assert (isinstance(A, np.ndarray) and isinstance(B, np.ndarray)),\
        "compareArrays: assert expecting ndarrays got {} {}"\
        .format(type(A), type(B))
    assert A.size == B.size, "compareArrays: assert equal size arrays failed"
    if A.shape != B.shape:
        A = flatten_1Ds(A)
        B = flatten_1Ds(B)
        assert len(A.shape) == len(B.shape),\
            "compareArrays: expecting same num dimension but got {} {}"\
            .format(len(A.shape), len(B.shape))
        if A.shape != B.shape:
            # maybe the shape dimensions are reversed
            assert A.shape[::-1] == B.shape,\
                "compareArrays: expecting similar shape arrays got {} {}"\
                .format(A.shape, B.shape)
            A = A.reshape(B.shape)
        assert A.shape == B.shape,\
            "compareArrays: expecting arrays to have the same shape got {} {}"\
            .format(A.shape, B.shape)
    if A.dtype.kind not in numpyAllNumCodes:
        # Not a numeric array
        return StatsEqual if np.array_equal(A, B) else StatsNotEqual
    # Numeric arrays
    if np.array_equal(A, B):
        return StatsEqual
    diff = abs((A / B) - 1)
    diff = np.nan_to_num(diff)
    histobins = [0, 0.005, .01, .02, .03, .04, .05, .06, .07, .09, .1, 1]
    histocounts, histobins = np.histogram(diff, histobins)
    result = {'mean': np.mean(diff), 'count': A.size,
              'min': np.min(diff), 'max': np.max(diff), 'stddev': np.std(diff),
              'histocounts': histocounts, 'histobins': histobins,
              'histopct': histocounts / A.size * 100}
    return result


def areArraysClose(A: np.ndarray, B: np.ndarray,
                   mean_limit=.01, stddev_limit=1.0) -> bool:
    '''Compare to arrays element-wise and compute the percent difference.
       Return True if the mean and stddev are withing the supplied limits.
       Default limits:{mean: .01, stddev: 1.0}, i.e. no stddev limit by default
    '''
    res = compareArrays(A, B)
    if res['mean'] > mean_limit:
        return False
    if res['stddev'] > stddev_limit:
        return False
    return True


class StructureMismatchError(ValueError):
    pass


def compareMatStructs(A: MatlabStructDict, B: MatlabStructDict,
                      field_list=None) -> dict:
    '''For each field, not like __*__, walk the fields and compare the values.
       If a field is missing from one of the structs raise an exception.
       If field_list is supplied, then only compare those fields.
       Return a dict with {fieldname: stat_results}.'''
    result = {}
    if field_list is None:
        field_list = A.fields()
    fieldSet = set(field_list)
    ASet = set(A.fields())
    BSet = set(B.fields())
    if not fieldSet <= ASet or not fieldSet <= BSet:
        raise StructureMismatchError(
            "missing fields: {}, {}".format(fieldSet - ASet, fieldSet - BSet))

    for key in field_list:
        valA = getattr(A, key)
        valB = getattr(B, key)
        if type(valA) != type(valB):
            raise StructureMismatchError(
                "field {} has different types {}, {}"
                .format(key, type(valA), type(valB)))
        if isinstance(valA, MatlabStructDict):
            stats = compareMatStructs(valA, valB)
            for subkey, subresult in stats.items():
                result[subkey] = subresult
        elif isinstance(valA, np.ndarray):
            stats = compareArrays(valA, valB)
            result[key] = stats
        else:
            diff = 0
            if isinstance(valA, numbers.Number):
                diff = abs((valA / valB) - 1)
            else:
                try:
                    diff = 0 if (valA == valB) else 1
                except ValueError:
                    print("Error comparing {} {} or type {}".format(
                        valA, valB, type(valA)))
                    raise
            stats = {'mean': diff, 'count': 1, 'min': diff, 'max': diff,
                     'stddev': 0, 'histocounts': None, 'histobins': None,
                     'histopct': None}
            result[key] = stats
    return result


def isMeanWithinThreshold(cmpStats: dict, threshold: float) -> bool:
    '''Examine all ßmean stats in dictionary and compare to threshold value'''
    means = [value['mean'] for key, value in cmpStats.items()]
    assert len(means) == len(cmpStats.keys()),\
        "isMeanWithinThreshold: assertion failed, length means mismatch {} {}"\
        .format(len(means), len(cmpStats.keys()))
    # for key, value in cmpStats.items():
    #     if value['mean'] > threshold:
    #         print(f"{key}: {value['mean']}")
    return all(mean <= threshold for mean in means if not np.isnan(mean))


def compareMatFiles(filename1: str, filename2: str) -> dict:
    '''Load both matlab files and call compareMatStructs.
       Inspect the resulting stats_result to see if any mean is
       beyond some threshold. Also print out the stats results.
       Return the result stats.
    '''
    matstruct1 = loadMatFile(filename1)
    matstruct2 = loadMatFile(filename2)
    if matstruct1.__name__ != matstruct2.__name__:
        raise StructureMismatchError(
            "Substructures don't match A {}, B {}"
            .format(matstruct1.__name__, matstruct2.__name__))
    result = compareMatStructs(matstruct1, matstruct2)
    return result


def pearsons_mean_corr(A: np.ndarray, B: np.ndarray):
    pearsonsList = []
    if A.shape != B.shape:
        A = flatten_1Ds(A)
        B = flatten_1Ds(B)
    if len(A.shape) == 1:
        A = A.reshape(A.shape[0], 1)
    if len(B.shape) == 1:
        B = B.reshape(B.shape[0], 1)
    assert(A.shape == B.shape)
    if len(A.shape) > 1:
        dims = A.shape
        if dims[1] > dims[0]:
            A = A.transpose()
            B = B.transpose()
    num_cols = A.shape[1]
    for col in range(num_cols):
        A_col = A[:, col]
        B_col = B[:, col]
        # ignore NaN values
        nans = np.logical_or(np.isnan(A_col), np.isnan(B_col))
        if np.all(nans == True):  # noqa - np.all needs == comparision not 'is'
            continue
        pearcol = sstats.pearsonr(A_col[~nans], B_col[~nans])
        pearsonsList.append(pearcol)
    pearsons = np.array(pearsonsList)
    if len(pearsons) == 0:
        return np.nan
    pearsons_mean = np.mean(pearsons[:, 0])
    return pearsons_mean
