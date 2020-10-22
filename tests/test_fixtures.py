"""
Test more complicated test fixtures, like BIDS Archives. Separate tests speed up
tests that use the fixtures, as the fixture doesn't have to be validated every
time it's created.
"""

from tests.common import isValidBidsArchive

"""
TODO(spolcyn): Support anatomical data

def testBidsArchive3D(bidsArchive3D):
    assert isValidBidsArchive(bidsArchive3D.rootPath), \
        "BIDS Archive 3D fixture is not a valid BIDS Archive"
"""


def testBidsArchive4D(bidsArchive4D):
    assert isValidBidsArchive(bidsArchive4D.rootPath), \
        "BIDS Archive 4D fixture is not a valid BIDS Archive"


def testBidsArchiveMultipleRun(bidsArchiveMultipleRuns):
    assert isValidBidsArchive(bidsArchiveMultipleRuns.rootPath), \
        "BIDS Archive Multiple Runs fixture is not a valid BIDS Archive " \
        "(path: " + bidsArchiveMultipleRuns.rootPath + " )"
