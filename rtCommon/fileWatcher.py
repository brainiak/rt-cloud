import os
import sys
import time
import logging
import threading
from queue import Queue, Empty
from watchdog.events import PatternMatchingEventHandler  # type: ignore
from rtCommon.utils import DebugLevels, demoDelay
from rtCommon.errors import StateError


class FileWatcher():
    """Virtual class for watching for the arrival of new files and reading them."""
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

    def waitForFile(self, specificFileName, timeout=0):
        logging.log(logging.ERROR, "FileWatcher is abstract class. waitForFile not implemented")
        return None


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

    def initFileNotifier(self, dir, filePattern, minFileSize, demoStep=0):
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

    def waitForFile(self, specificFileName, timeout=0):
        fileExists = os.path.exists(specificFileName)
        if not fileExists:
            if self.observer is None:
                raise FileNotFoundError("No fileNotifier and dicom file not found %s" % (specificFileName))
            else:
                logStr = "FileWatcher: Waiting for file {}, timeout {}s ".format(specificFileName, timeout)
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
            except Empty as err:
                # The timeout occured on fileNotifyQ.get()
                fileExists = os.path.exists(specificFileName)
                continue
            if event is None:
                raise StateError('waitForFile: event is None')
            # We may have a stale event from a previous file if multiple events
            #   are created per file or if the previous file eventloop
            #   timed out and then the event arrived later.
            if event.src_path == specificFileName:
                fileExists = True
                exitWithFileEvent = True
                eventTimeStamp = ts
                continue
            if time.time() > timeToCheckForFile:
                # periodically check if file exists, can occur if we get
                #   swamped with unrelated events
                fileExists = os.path.exists(specificFileName)
                timeToCheckForFile = time.time() + 1

        # wait for the full file to be written, wait at most 300 ms
        waitIncrement = 0.1
        totalWriteWait = 0.0
        fileSize = os.path.getsize(specificFileName)
        while fileSize < self.minFileSize and totalWriteWait < 0.3:
            time.sleep(waitIncrement)
            totalWriteWait += waitIncrement
            fileSize = os.path.getsize(specificFileName)
        logging.log(DebugLevels.L6,
                    "File avail: eventLoopCount %d, writeWaitTime %.3f, "
                    "fileEventCaptured %s, fileName %s, eventTimeStamp %.5f",
                    eventLoopCount, totalWriteWait,
                    exitWithFileEvent, specificFileName, eventTimeStamp)
        if self.demoStep is not None and self.demoStep > 0:
            self.prevEventTime = demoDelay(self.demoStep, self.prevEventTime)
        return specificFileName


class FileNotifyHandler(PatternMatchingEventHandler):  # type: ignore
    def __init__(self, q, patterns):
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

    def initFileNotifier(self, dir, filePattern, minFileSize, demoStep=0):
        # inotify doesn't use filepatterns
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

    def waitForFile(self, specificFileName, timeout=0):
        fileExists = os.path.exists(specificFileName)
        if not fileExists:
            if self.notify_thread is None:
                raise FileNotFoundError("No fileNotifier and dicom file not found %s" % (specificFileName))
            else:
                logStr = "FileWatcher: Waiting for file {}, timeout {}s ".format(specificFileName, timeout)
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
            except Empty as err:
                # The timeout occured on fileNotifyQ.get()
                fileExists = os.path.exists(specificFileName)
                continue
            if eventfile is None:
                raise StateError('waitForFile: eventfile is None')
            # We may have a stale event from a previous file if multiple events
            #   are created per file or if the previous file eventloop
            #   timed out and then the event arrived later.
            if eventfile == specificFileName:
                fileExists = True
                exitWithFileEvent = True
                eventTimeStamp = ts
                continue
            if time.time() > timeToCheckForFile:
                # periodically check if file exists, can occur if we get
                #   swamped with unrelated events
                fileExists = os.path.exists(specificFileName)
                timeToCheckForFile = time.time() + 1
        if exitWithFileEvent is False:
            # We didn't get a file-close event because the file already existed.
            # Check the file size and sleep up to 300 ms waitig for full size
            waitIncrement = 0.1
            totalWriteWait = 0.0
            fileSize = os.path.getsize(specificFileName)
            while fileSize < self.minFileSize and totalWriteWait < 0.3:
                time.sleep(waitIncrement)
                totalWriteWait += waitIncrement
                fileSize = os.path.getsize(specificFileName)
        logging.log(DebugLevels.L6,
                    "File avail: eventLoopCount %d, fileEventCaptured %s, "
                    "fileName %s, eventTimeStamp %d", eventLoopCount,
                    exitWithFileEvent, specificFileName, eventTimeStamp)
        if self.demoStep is not None and self.demoStep > 0:
            self.prevEventTime = demoDelay(self.demoStep, self.prevEventTime)
        return specificFileName

    def notifyEventLoop(self):
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
