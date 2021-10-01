import os
import pytest
import shutil
import tempfile
import subprocess
import rtCommon.openNeuroInterface as openNeuro

def test_openNeuroInterface():
    tmpDir = tempfile.gettempdir()
    onInterface = openNeuro.OpenNeuroInterface(tmpDir)

    datasets = onInterface.getDatasetList()
    assert len(datasets) > 625

    subjects = onInterface.getSubjectList('ds002338')
    expectedList = \
        ['xp201', 'xp202', 'xp203', 'xp204', 'xp205', 'xp206',
         'xp207', 'xp210', 'xp211', 'xp213', 'xp216', 'xp217',
         'xp218', 'xp219', 'xp220', 'xp221', 'xp222']
    assert subjects == expectedList

    desc = onInterface.getDescription('ds002338')
    assert type(desc) is dict and len(desc.get('Name')) > 0

    readme = onInterface.getReadme('ds002338')
    assert readme is not None and len(readme) > 0


def test_openNeuroDownloads():
    tmpDir = tempfile.gettempdir()
    print()
    print(f"## USE {tmpDir}")
    onInterface = openNeuro.OpenNeuroInterface(tmpDir)

    accessionNumber = 'ds003194'
    dsPath = os.path.join(tmpDir, accessionNumber)
    # remove all files in this path
    shutil.rmtree(dsPath, ignore_errors=True)

    onInterface.downloadData(accessionNumber)
    assert fileCount(dsPath) == 6

    subj = 'NEPO01'
    onInterface.downloadData(accessionNumber, subject=subj)
    assert fileCount(os.path.join(dsPath, 'sub-' + subj)) == 10

    subj = 'NEPO03'
    onInterface.downloadData(accessionNumber, subject=subj, task='task6mnepo')
    assert fileCount(os.path.join(dsPath, 'sub-' + subj)) == 4

    subj = 'NEPO04'
    onInterface.downloadData(accessionNumber, subject=subj, session='nepo6m')
    assert fileCount(os.path.join(dsPath, 'sub-' + subj)) == 5

    subj = 'NEPO06'
    onInterface.downloadData(accessionNumber, subject=subj, session='nepo6m', task='task6mnepo')
    assert fileCount(os.path.join(dsPath, 'sub-' + subj)) == 4

    # # This is a larger download, commenting out for now
    # accessionNumber = 'ds001345'
    # dsPath = os.path.join(tmpDir, accessionNumber)
    # # remove all files in this path
    # shutil.rmtree(dsPath, ignore_errors=True)
    # onInterface.downloadData(accessionNumber, subject='01', run=4)
    # assert fileCount(os.path.join(dsPath, 'sub-' + '01')) == 2

    # # This is a larger download, commenting out for now
    # accessionNumber = 'ds000234'
    # dsPath = os.path.join(tmpDir, accessionNumber)
    # # remove all files in this path
    # shutil.rmtree(dsPath, ignore_errors=True)
    # subj = '03'
    # onInterface.downloadData(accessionNumber, subject=subj ,task='motorphotic')
    # assert fileCount(os.path.join(dsPath, 'sub-' + subj)) == 2


def fileCount(path):
    if not os.path.exists(path):
        return 0
    cmd = f'find {path} -type file | wc -l'
    cmdList = cmd.split(' ')
    # Only seems to work with shell=True, maybe because of the pipe to wc
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE)
    count = result.stdout.decode('utf-8')
    count = count.lstrip().rstrip()
    return int(count)
