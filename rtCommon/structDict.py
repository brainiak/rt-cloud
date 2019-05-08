"""
StructDictClass - contains classes StructDict and MatlabStructDict to make it
    possible to access a dictionary with syntax struct.field.
"""

import re
import typing
import numpy as np  # type: ignore


class StructDict(dict):
    '''Class that adds a structure type syntax to dictionaries,
       i.e. 'dict.field' will invoke dict['field']
    '''

    def __getattr__(self, key):
        '''Implement getattr to support syntax "data.field"'''
        try:
            val = self[key]
        except KeyError:
            val = None
        return val

    def __setattr__(self, key, val):
        '''Implement setattr to support syntax "data.field=x"'''
        self[key] = val

    def __delattr__(self, key):
        '''Implement delattr to support syntax "del data.field"'''
        if key in self:
            del self[key]

    def __getstate__(self):
        '''Needed for pickling, return the underlying dictionary'''
        return dict(self)

    def __setstate__(self, dict_entries):
        '''Needed for pickling, set the underlying dictionary'''
        self.update(dict_entries)

    def copy(self):
        return StructDict(super().copy())


def copy_toplevel(data):
    cptl = StructDict()
    for key, val in data.items():
        if isinstance(val, dict):
            continue
        if type(val) == list:
            if isinstance(val[0], dict):
                continue
        cptl[key] = val
    return cptl


def recurseCreateStructDict(data):
    '''Given a recursive dictionary, i.e. a dictionary that has
            child dictionaries or lists of dictionaries,
            convert each child dictionary to a StructDict.
      '''
    if isinstance(data, dict):
        tmpDict = StructDict()
        for key, value in data.items():
            tmpDict[key] = recurseCreateStructDict(value)
        return tmpDict
    elif isinstance(data, list):
        tmpList = []
        for value in data:
            tmpList.append(recurseCreateStructDict(value))
        return tmpList
    return data


# Class to make it easier to access fields in matlab structs loaded into python
class MatlabStructDict(StructDict):
    '''Subclass dictionary so that elements can be accessed either as dict['key']
        of dict.key. If elements are of type NumPy structured arrays, convert
        them to dictionaries and then to MatlabStructDict also.
    '''

    def __init__(self, dictionary, name=None):
        # name is used to identify a special child dictionary whose elements
        #  should be considered as top level elements. i.e. if name=patterns,
        #  then data.patterns.field will return the same as data.field
        self.__name__ = name
        super().__init__(dictionary)
        # Convert any numpy structured arrays to MatlabStructDict
        for key in self.keys():
            try:
                # structured arrays will have a non-zero length set of names
                #  i.e. len(self[key].dtype.names) > 0
                if (isinstance(self[key], np.ndarray) and
                        len(self[key].dtype.names) > 0):
                    self[key] = MatlabStructDict(
                        convertStructuredArrayToDict(self[key]))
            except TypeError:
                pass

    def __getattr__(self, key):
        '''Implement getattr to support syntax x=data.field'''
        struct = self
        # if the key isn't found at the top level, check if it is a sub-field
        # of the special 'name' child dictionary
        if key not in self.keys() and self.__name__ in self.keys():
            struct = self[self.__name__]
        try:
            val = struct[key]
        except KeyError:
            val = None
        # flatten numpy arrays
        while isinstance(val, np.ndarray) and val.shape == (1, 1):
            val = val[0][0]
        return val

    def __setattr__(self, key, val):
        '''Implement setattr to support syntax data.field=x'''
        # check for special __fields__ and do default handling
        if re.match('__.*__', key):
            super().__setattr__(key, val)
            return
        # if the key isn't found at the top level, check if it is a sub-field
        # of the special 'name' field so we can set the value there
        struct = self
        if key not in self.keys() and self.__name__ in self.keys():
            if key in self[self.__name__].keys():
                struct = self[self.__name__]

        # pack ints in 2d array [[int]] as matlab does
        if isinstance(val, int):
            field_type = None
            if val in range(256):
                field_type = np.uint8
            struct[key] = np.array([[val]], dtype=field_type)
        else:
            struct[key] = val

    def copy(self):
        return MatlabStructDict(super().copy(), self.__name__)

    def fields(self):
        '''list all fields including subfields of the special 'name' field'''
        struct_fields: typing.List = []
        try:
            struct = self[self.__name__]
            if isinstance(struct, StructDict):
                struct_fields = list(struct.keys())
        except KeyError:
            pass
        allfields: typing.Set = set().union(list(self.keys()), struct_fields)
        regfields = set(
            [field for field in allfields if not re.match('__.*__', field)])
        return regfields


# Data loaded from matlab is as a structured array. But it's not easy to add
#  new fields to a structured array, so convert it to a dictionary
#  for easier use.
def convertStructuredArrayToDict(sArray):
    '''Convert a NumPy structured array to a dictionary.'''
    rvDict = dict()
    for key in sArray.dtype.names:
        try:
            val = sArray[key]
            # Check for and flatten arrays with only one element in them
            if isinstance(val, np.ndarray) and val.shape == (1, 1):
                val = val[0][0]
            rvDict[key] = val
        except KeyError:
            pass
    return rvDict


def isStructuredArray(var) -> bool:
    '''Return True if var is a numpy structured array'''

    if (isinstance(var, np.ndarray) and
            var.dtype.names is not None and
            len(var.dtype.names) > 0):
        return True
    else:
        return False
