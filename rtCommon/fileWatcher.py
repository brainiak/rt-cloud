"""
FileWatcher implements a class that watches for files to be created in a directory and then
returns the notification that the files is now available.

The FileWatcher class is a virtual class of sorts with two underlying implementations, one
for Mac and Windows (WatchdogFileWatcher) and one for Linux (InotifyFileWatcher).
"""
import os
import sys
import time
import logging
import threading
from typing import Optional
from queue import Queue, Empty
from watchdog.events import PatternMatchingEventHandler  # type: ignore
from rtCommon.utils import DebugLevels, demoDelay
from rtCommon.errors import StateError


class FileWatcher():
    """Virtual class to watch for the arrival of new files and notify."""
    def __new__(cls):
        if sys.platform in ("linux", "linux2"):
            # create linux version
            newcls = InotifyFileWatcher.__new__(InotifyFileWatcher)
            newcls.__init__()
            return newcls
        elif sys.platform in ("darwin", "win32"):
            # create Mac/Windows version
            newcls = WatchdogFileWatcher.__new__(WatchdogFileWatcher)
            newcls.__init__()
            return newcls
        else:
            # unsupported os type
            logging.log(logging.ERROR, "Unsupported os type %s" % (sys.platform))
            return None

    def __init__(self):
        logging.log(logging.ERROR, "FileWatcher is abstract class. __init__ not implemented")

    def __del__(self):
        logging.log(logging.ERROR, "FileWatcher is abstract class. __del__ not implemented")

    def initFileNotifier(self, dir, filePattern, minFileSize, demoStep=0):
        logging.log(logging.ERROR, "FileWatcher is abstract class. initFileNotifier not implemented")
        return None

    def waitForFile(self, filename, timeout=0):
        logging.log(logging.ERROR, "FileWatcher is abstract class. waitForFile not implemented")
        return ''


if sys.platform in ("darwin", "win32"):
    from watchdog.observers import Observer  # type: ignore


# Version of FileWatcher for Mac and Windows
class WatchdogFileWatcher():
    """Version of FileWatcher for Mac and Windows using Watchdog toolkit."""
    def __init__(self):
        self.observer = None
        self.fileNotifyHandler = None
        self.fileNotifyQ = Queue()  # type: None
        self.filePattern = None
        self.watchDir = None
        self.minFileSize = 0
        self.demoStep = 0
        self.prevEventTime = 0

    def __del__(self):
        if self.observer is not None:
            try:
                self.observer.stop()
            except Exception as err:
                # TODO - change back to log once can figure out what the observer.stop streamRef error is
                print("FileWatcher: oberver.stop(): %s", str(err))

    def initFileNotifier(self, dir: str, filePattern: str, minFileSize: int, demoStep: int=0) -> None:
        """
        Initialize the file watcher to watch in the specified directory for the specified
        regex-based filepattern.
        Args:
            dir (str): Directory to watch in
            filePattern (str): Regex-based filepattern to watch for
            minFileSize (int): Minimum file size necessary to consider the file is wholely written.
                Below this size the filewatcher will assume file is paritally written and continue
                to wait.
            demoStep (int): If non-zero then it will space out file notifications by demoStep seconds.
                This is used when the image files are pre-existing but we want to simulate as if
                the arrive from the scanner every few seconds (demoStep seconds).
        """
        self.demoStep = demoStep
        self.minFileSize = minFileSize
        if self.observer is not None:
            self.observer.stop()
        self.observer = Observer()
        if filePattern is None or filePattern == '':
            filePattern = '*'
        self.filePattern = filePattern
        self.watchDir = dir
        self.fileNotifyHandler = FileNotifyHandler(self.fileNotifyQ, [filePattern])
        self.observer.schedule(self.fileNotifyHandler, dir, recursive=False)
        self.observer.start()

    def waitForFile(self, filename: str, timeout: int=0) -> Optional[str]:
        """
        Wait for a specific filename to be created in the directory specified in initFileNotifier.
        Args:
            filename: Name of File to watch for creation of. If filename includes a path it must 
                match that specified in initFileNotifier.
            timeout: Max number of seconds to watch for the file creation. If timeout expires
                before the file is created then None will be returned
        Returns:
            The filename of the created file (same as input arg) or None if timeout expires
        """
        _filedir, _filename = os.path.split(filename)
        if _filedir in (None, ''):
            filename = os.path.join(self.watchDir, filename)
        elif _filedir != self.watchDir:
            raise StateError(f"FileWatcher: file path doesn't match watch directory: {_filedir}, {self.watchDir}")

        fileExists = os.path.exists(filename)
        if not fileExists:
            if self.observer is None:
                raise FileNotFoundError("No fileNotifier and dicom file not found %s" % (filename))
            else:
                logStr = "FileWatcher: Waiting for file {}, timeout {}s ".format(filename, timeout)
                logging.log(DebugLevels.L6, logStr)
        eventLoopCount = 0
        exitWithFileEvent = False
        eventTimeStamp = 0
        startTime = time.time()
        timeToCheckForFile = time.time() + 1  # check if file exists at least every second
        while not fileExists:
            if timeout > 0 and time.time() > (startTime + timeout):
                return None
            # look for file creation event
            eventLoopCount += 1
            try:
                event, ts = self.fileNotifyQ.get(block=True, timeout=1.0)
            except Empty:
                # The timeout occured on fileNotifyQ.get()
                fileExists = os.path.exists(filename)
                continue
            if event is None:
                raise StateError('waitForFile: event is None')
            # We may have a stale event from a previous file if multiple events
            #   are created per file or if the previous file eventloop
            #   timed out and then the event arrived later.
            if event.src_path == filename:
                fileExists = True
                exitWithFileEvent = True
                eventTimeStamp = ts
                continue
            if time.time() > timeToCheckForFile:
                # periodically check if file exists, can occur if we get
                #   swamped with unrelated events
                fileExists = os.path.exists(filename)
                timeToCheckForFile = time.time() + 1

        # wait for the full file to be written, wait at most 300 ms
        waitIncrement = 0.1
        totalWriteWait = 0.0
        fileSize = os.path.getsize(filename)
        while fileSize < self.minFileSize and totalWriteWait < 0.3:
            time.sleep(waitIncrement)
            totalWriteWait += waitIncrement
            fileSize = os.path.getsize(filename)
        logging.log(DebugLevels.L6,
                    "File avail: eventLoopCount %d, writeWaitTime %.3f, "
                    "fileEventCaptured %s, fileName %s, eventTimeStamp %.5f",
                    eventLoopCount, totalWriteWait,
                    exitWithFileEvent, filename, eventTimeStamp)
        if self.demoStep is not None and self.demoStep > 0:
            self.prevEventTime = demoDelay(self.demoStep, self.prevEventTime)
        return filename


class FileNotifyHandler(PatternMatchingEventHandler):  # type: ignore
    """
    Handler class that will receive the watchdog notifications. It will queue the notifications
    int the queue provided during to the init function.
    """
    def __init__(self, q, patterns):
        """
        Args:
            q (queue): Queue into which file-creation notifications will be placed.
            patterns (List[regex]): Filename patterns to watch for.
        """
        super().__init__(patterns=patterns)
        self.q = q

    def on_created(self, event):
        self.q.put((event, time.time()))

    def on_modified(self, event):
        self.q.put((event, time.time()))


# import libraries for Linux version
if sys.platform in ("linux", "linux2"):
    import inotify
    import inotify.adapters


# Version of FileWatcher for Linux
class InotifyFileWatcher():
    """Version of FileWatcher for Linux using Inotify interface."""
    def __init__(self):
        self.watchDir = None
        self.minFileSize = 0
        self.shouldExit = False
        self.demoStep = 0
        self.prevEventTime = 0
        # create a listening thread
        self.fileNotifyQ = Queue()  # type: None
        self.notifier = inotify.adapters.Inotify()
        self.notify_thread = threading.Thread(name='inotify', target=self.notifyEventLoop)
        self.notify_thread.setDaemon(True)
        self.notify_thread.start()

    def __del__(self):
        self.shouldExit = True
        self.notify_thread.join(timeout=2)

    def initFileNotifier(self, dir: str, filePattern: str, minFileSize: int, demoStep: int=0) -> None:
        """
        Initialize the file watcher to watch for files in the specified directory.
        Note: inotify doesn't use filepatterns

        Args:
            dir (str): Directory to watch in
            filePattern (str): ignored by inotify implementation
            minFileSize (int): Minimum file size necessary to consider the file is wholely written.
                Below this size the filewatcher will assume file is paritally written and continue
                to wait.
            demoStep (int): If non-zero then it will space out file notifications by demoStep seconds.
                This is used when the image files are pre-existing but we want to simulate as if
                the arrive from the scanner every few seconds (demoStep seconds).
        """
        self.demoStep = demoStep
        self.minFileSize = minFileSize
        if dir is None:
            raise StateError('initFileNotifier: dir is None')
        if not os.path.exists(dir):
            raise NotADirectoryError("No such directory: %s" % (dir))
        if dir != self.watchDir:
            if self.watchDir is not None:
                self.notifier.remove_watch(self.watchDir)
            self.watchDir = dir
            self.notifier.add_watch(self.watchDir, mask=inotify.constants.IN_CLOSE_WRITE)

    def waitForFile(self, filename: str, timeout: int=0) -> Optional[str]:
        """
        Wait for a specific filename to be created in the directory specified in initFileNotifier.
        Args:
            filename: Name of File to watch for creation of. If filename includes a path it must 
                match that specified in initFileNotifier.
            timeout: Max number of seconds to watch for the file creation. If timeout expires
                before the file is created then None will be returned
        Returns:
            The filename of the created file (same as input arg) or None if timeout expires
        """
        _filedir, _filename = os.path.split(filename)
        if _filedir in (None, ''):
            filename = os.path.join(self.watchDir, filename)
        elif _filedir != self.watchDir:
            raise StateError(f"FileWatcher: file path doesn't match watch directory: {_filedir}, {self.watchDir}")

        fileExists = os.path.exists(filename)
        if not fileExists:
            if self.notify_thread is None:
                raise FileNotFoundError("No fileNotifier and dicom file not found %s" % (filename))
            else:
                logStr = "FileWatcher: Waiting for file {}, timeout {}s ".format(filename, timeout)
                logging.log(DebugLevels.L6, logStr)
        eventLoopCount = 0
        exitWithFileEvent = False
        eventTimeStamp = 0
        startTime = time.time()
        timeToCheckForFile = time.time() + 1  # check if file exists at least every second
        while not fileExists:
            if timeout > 0 and time.time() > (startTime + timeout):
                return None
            # look for file creation event
            eventLoopCount += 1
            try:
                eventfile, ts = self.fileNotifyQ.get(block=True, timeout=1.0)
            except Empty:
                # The timeout occured on fileNotifyQ.get()
                fileExists = os.path.exists(filename)
                continue
            if eventfile is None:
                raise StateError('waitForFile: eventfile is None')
            # We may have a stale event from a previous file if multiple events
            #   are created per file or if the previous file eventloop
            #   timed out and then the event arrived later.
            if eventfile == filename:
                fileExists = True
                exitWithFileEvent = True
                eventTimeStamp = ts
                continue
            if time.time() > timeToCheckForFile:
                # periodically check if file exists, can occur if we get
                #   swamped with unrelated events
                fileExists = os.path.exists(filename)
                timeToCheckForFile = time.time() + 1
        if exitWithFileEvent is False:
            # We didn't get a file-close event because the file already existed.
            # Check the file size and sleep up to 300 ms waitig for full size
            waitIncrement = 0.1
            totalWriteWait = 0.0
            fileSize = os.path.getsize(filename)
            while fileSize < self.minFileSize and totalWriteWait < 0.3:
                time.sleep(waitIncrement)
                totalWriteWait += waitIncrement
                fileSize = os.path.getsize(filename)
        logging.log(DebugLevels.L6,
                    "File avail: eventLoopCount %d, fileEventCaptured %s, "
                    "fileName %s, eventTimeStamp %d", eventLoopCount,
                    exitWithFileEvent, filename, eventTimeStamp)
        if self.demoStep is not None and self.demoStep > 0:
            self.prevEventTime = demoDelay(self.demoStep, self.prevEventTime)
        return filename

    def notifyEventLoop(self):
        """
        Thread function which gets notifications and queues them in the fileNotifyQ
        """
        for event in self.notifier.event_gen():
            if self.shouldExit is True:
                break
            if event is not None:
                # print(event)      # uncomment to see all events generated
                if 'IN_CLOSE_WRITE' in event[1]:
                    fullpath = os.path.join(event[2], event[3])
                    self.fileNotifyQ.put((fullpath, time.time()))
                else:
                    self.fileNotifyQ.put(('', time.time()))
