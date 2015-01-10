#!/usr/bin/python3
__author__ = 'eayin'
__version__ = '0.1.0'

import traceback
import os
import logging
import logging.handlers
import sys
import heapq
import time
import re
import copy
import inspect
import errno

from math import ceil
from subprocess import Popen, PIPE
from argparse import ArgumentParser, ArgumentTypeError
from collections import defaultdict

app_name = os.path.splitext(os.path.basename(__file__))[0]


class ColoredConsoleHandler(logging.StreamHandler):
    def emit(self, record):
        # Need to make a actual copy of the record
        # to prevent altering the message for other loggers
        myrecord = copy.copy(record)
        levelno = myrecord.levelno
        if(levelno >= 50):  # CRITICAL / FATAL
            color = '\x1b[31m'  # red
        elif(levelno >= 40):  # ERROR
            color = '\x1b[31m'  # red
        elif(levelno >= 30):  # WARNING
            color = '\x1b[33m'  # yellow
        elif(levelno >= 20):  # INFO
            color = '\x1b[32m'  # green
        elif(levelno >= 10):  # DEBUG
            color = '\x1b[35m'  # pink
        else:  # NOTSET and anything else
            color = '\x1b[0m'  # normal
        myrecord.msg = color + str(myrecord.msg) + '\x1b[0m'  # normal
        logging.StreamHandler.emit(self, myrecord)

#### Functions
def logInfo(message):
    "Automatically log the current function details."
    # Get the previous frame in the stack, otherwise it would be this function.
    func = inspect.currentframe().f_back.f_code
    logger.info("%s:%i  %s" % (func.co_name, func.co_firstlineno, message))

def logError(message):
    func = inspect.currentframe().f_back.f_code
    logger.error("%s:%i  %s" % (func.co_name, func.co_firstlineno, message))

def logWarning(message):
    func = inspect.currentframe().f_back.f_code
    logger.warning("%s:%i  %s" % (func.co_name, func.co_firstlineno, message))

def logDebug(message):
    func = inspect.currentframe().f_back.f_code
    logger.debug("%s:%i  %s" % (func.co_name, func.co_firstlineno, message))

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            logError("Could not create directory")
            raise

def evenSpread(sequence, num):
    length = float(len(sequence))
    for i in range(num):
        yield sequence[int(ceil(i * length / num))]

def sendmail(event, subject, message):
    p = Popen(["/usr/bin/gymail.py", "-e", event, "-s", subject, "-m", message], stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()

def checkPath(string):
    value = str(string)
    if string[-1:] != "/":
        msg = "%r subvolume is not ending with a slash. It should be e.g.: /home/ and not /home." % string
        raise ArgumentTypeError(msg)
    return value

def checkTimespan(string):
    stringList = string.split(",")
    daysList = []
    for element in stringList:
        match = re.search("([0-9]+)([m|w])=([0-9]+)", element)
        if match.group(2) == "w":
            days = int(match.group(1))*7
        elif match.group(2) == "m":
            days = int(match.group(1))*30
        else:
            msg = "%r Only w (for weeks) and m (for months) are accepted syntax." % string
            raise ArgumentTypeError(msg)
        if is_number(match.group(3)) is False:
            msg = "%s Keep Value is not a number." % string
            raise ArgumentTypeError(msg)
        daysList.append(days)
    if sorted(daysList) == daysList:
        pass
    else:
        msg = "%r time spans are unsorted." % string
        raise ArgumentTypeError(msg)
    return string

def touch(fname, times=None):
    with open(fname, 'a'):
        os.utime(fname, times)


class Bytterfs:

    def __init__(self, snapshotName, source, destRootSubvol, destContainer, keep, sshHost, sshPort, sshKey):
        self.snapshotName = snapshotName
        self.source = source
        self.destContainer = destContainer
        self.destRootSubvol = destRootSubvol
        self.keep = keep
        self.sshHost = sshHost
        self.sshPort = sshPort
        self.sshKey = sshKey
        self.sshArgs = ["ssh", "-i", self.sshKey, "-p", self.sshPort, self.sshHost, "-t"]
        self.lockfile = "%s%s" % (self.source, "bytterfs.lock")

    def inc(self, newSnapshot, prevSnapshot):
        logInfo("Creating /bytterfs.lockfile and beginning incremental backup.")
        prevSnapshot = os.path.basename(os.path.normpath(prevSnapshot))
        logDebug("Snapshot with stripped path and appended source: %s%s" % (self.source, prevSnapshot))
        newSnapshot = os.path.basename(os.path.normpath(newSnapshot))
        logDebug("Snapshot with stripped path and appended source: %s%s" % (self.source, newSnapshot))
        touch(self.lockfile)
        p1 = Popen(["sudo", "btrfs", "send", "-p", "%s%s" % (self.source, prevSnapshot),
                    "%s%s" % (self.source, newSnapshot)], stdout=PIPE)
        p2 = Popen(self.sshArgs + ["sudo", "btrfs", "receive", self.destContainer], stdin=p1.stdout, stdout=PIPE)
        p1.stdout.close()
        out, err = p2.communicate()
        if p2.returncode != 0:
            logError("Error when doing incremental backup. Sending Mail and exiting. Output:%s Error: "
                     "%s" % (out, err))
            sendmail("error", "Bytterfs", "Error when doing incremental backup. Output:%s Error: %s" % (out, err))
            exit(0)
        logDebug("subprocess output: %s \nsubprocess error: %s" % (out, err))
        os.remove(self.lockfile)
        logInfo('destKeepSnapshots()')
        self.destKeepSnapshots()
        logInfo('clientDeleteOlderSnapshots()')
        self.clientDeleteOlderSnapshots()
        logInfo('Backup %s created successfully' % self.snapshotName)
        exit(0)

    def full(self, snapshot):
        logInfo("Creating /bytterfs.lockfile and beginning full backup.")
        touch(self.lockfile)
        snapshot = os.path.basename(os.path.normpath(snapshot))
        logDebug("Snapshot with stripped path and appended source: %s%s" % (self.source, snapshot))
        p1 = Popen(["sudo", "btrfs", "send", "%s%s" % (self.source, snapshot)], stdout=PIPE)
        p2 = Popen(self.sshArgs + ["sudo", "btrfs", "receive", self.destContainer], stdin=p1.stdout, stdout=PIPE)
        p1.stdout.close()
        out, err = p2.communicate()
        if p2.returncode != 0:
            logError("Error when doing full backup. Sending Mail and exiting. Output:%s Error: %s"
                     % (out, err))
            sendmail("error", "Bytterfs", "Error when doing full backup. Output:%s Error: %s" % (out, err))
            exit(0)
        logInfo("subprocess output: %s \nsubprocess error: %s" % (out, err))
        os.remove(self.lockfile)
        logInfo('destKeepSnapshots()')
        self.destKeepSnapshots()
        logInfo('clientDeleteOlderSnapshotss()')
        self.clientDeleteOlderSnapshots()
        logInfo('Backup %s created successfully' % self.snapshotName)
        exit(0)

    def subvolSplitTsList(self, subvolList):
        tsList = []
        for subvol in subvolList:
            try:
                tsList.append(subvol.split("_")[1])  ## was subvol[0] not sure why
            except:
                logError("There's a snapshot that has a wrong naming syntax. Exiting backup and sending mail.")
                sendmail("error", "Bytterfs", "There's a snapshot that has a wrong naming syntax. Exiting backup.")
        return sorted(tsList)

    def isLockfile(self):
        if os.path.isfile(self.lockfile) is False:
            logInfo("No lockfile found. Seems last backup was not interrupted. Continuing. \n")
            pass
        else:
            logError("Lockfile found. Last backup was interrupted. Deleting possible incomplete snapshot on "
                     "destination.\n")
            sendmail("error", "Bytterfs", "Lockfile found. Deleting possible left over on destination and continuing "
                     "with backup. See local syslog for more details.")
            clientSubvolList = self.clientSubvolList(withUUID=False)  # verified that it's clean (doesnt contain \n or \r)
            clientTsList = self.subvolSplitTsList(clientSubvolList)
            destTsList = self.subvolSplitTsList(self.destSubvolList(withUUID=False))
            destLatestSnapshot = self.destLatestSnapshot()
            if destLatestSnapshot is None:
                logError("No Snapshots found on destination. Something is wrong. Exiting and sending mail.")
                sendmail("error", "Bytterfs","No Snapshots found on destination. Something is wrong.")
                exit(0)
            if len(clientSubvolList) == 0:
                logWarning("isLockfile(): Found no snapshots on client.")
                self.destDeleteSubvol(destLatestSnapshot)
                self.full(self.clientCreateSnapshot())
            elif len(clientSubvolList) == 1:
                logWarning("isLockfile(): Found one snapshot on client.")
                logDebug("Checking if destHasSnapshot(clientTsList[0]), where clientTsList[0] is: %s" % clientTsList[0])
                if self.destHasSnapshot(clientTsList[0]):
                    logWarning("isLockfile(): Found client snapshot on destination. Deleting it, because it might be "
                               "incomplete.")
                    self.destDeleteSubvol(destLatestSnapshot)
                    self.full(clientSubvolList[0])
                else:
                    logWarning("isLockfile(): Did not find client snapshot on destination.")
                    self.full(clientSubvolList[0])
            elif len(clientSubvolList) > 1 and len(destTsList) > 1:
                logWarning("isLockfile(): Found more than one snapshot on client. Deleting all snapshots on client"
                           "that are not found on dest. and moreover deleting the newest snapshot that is "
                           "found on client and dest. So we iterate over all client snapshots and check if it is"
                           "the newest on the destination. Moreover it checks for a previous snapshot which is"
                           "both on client and dest, so that an incremental backup can be done. Also delete"
                           "last snapshot on client after deleting it on dest. instead creata a new snapshot"
                           "on client and get the previous snapshot on dest / client.")
                # Alternatively the last snapshot that is found on destination could be deleted.
                clientTsTmpList = []
                for ts in clientTsList:
                    if ts == self.destNewestSnapshot():
                        # Delete Newest Snapshot on destination
                        self.destDeleteSubvol("%s_%s" % (self.snapshotName, ts))
                        for ts2 in clientTsList:
                            if ts2 < ts:
                                clientTsTmpList.append(ts2)
                        for ts3 in sorted(clientTsTmpList):
                            if self.destHasSnapshot(ts3):
                                newSnapshot = self.clientCreateSnapshot()
                                self.inc(newSnapshot, "%s_%s" % (self.snapshotName, ts3))
                self.destDeleteSubvol("%s_%s" % (self.snapshotName, self.destNewestSnapshot()))
                newSnapshot = self.clientCreateSnapshot()
                self.full(newSnapshot)
            elif len(clientSubvolList) > 1 and len(destTsList) == 0:
                logWarning("Found more than one snapshot on client, but found no snapshot on dest.")
                newSnapshot = self.clientCreateSnapshot()
                # no need del redundant snapshots here, bcs later clientDeleteOlderSnapshots does that
                self.full(newSnapshot)
            elif len(clientSubvolList) > 1 and len(destTsList) == 1:
                logWarning("Found more than one snapshot on client and found one snapshot on dest.")
                self.destDeleteSubvol("%s_%s" % (self.snapshotName, self.destNewestSnapshot()))
                newSnapshot = self.clientCreateSnapshot()
                self.full(newSnapshot)

    def initiateBackup(self):
        subvolList = self.clientSubvolList(withUUID=True)
        if len(subvolList) == 0:
            logError("Found no snapshot on client. Sending mail. Ignore this error, if you run bytterfs the first time")
            sendmail("error", "Bytterfs", "Found no snapshot on client. Ignore error, if you run    bytterfs first time.")
            newSnapshot = self.clientCreateSnapshot()
            self.full(newSnapshot)
        elif len(subvolList) >= 1:
            logInfo("Found one or more than one matching snapshot on client. Checking if dest has subvol of client and "
                     "then proceeding with backup.")
            clientLatestTs = self.clientLatestSnapshot(onlyTs=True)
            logInfo("Checking if clientLatestTs: %s is on destination." % clientLatestTs)
            if self.destHasSnapshot(clientLatestTs) is True:
                logInfo("Found clientLatestTs on destination. Initiating incremental backup")
                newSnapshot = self.clientCreateSnapshot()
                self.inc(newSnapshot, "%s_%s" % (self.snapshotName, clientLatestTs))
            elif self.destHasSnapshot(clientLatestTs) is False:
                logInfo("Did not find clientLatestTs on destination. Initiating full backup")
                self.full("%s_%s" % (self.snapshotName, clientLatestTs))

    def clientLatestSnapshot(self, onlyTs):
        clientTsList = self.subvolSplitTsList(self.clientSubvolList(withUUID=False))
        if onlyTs is True:
            return heapq.nlargest(1, clientTsList)[0]
        else:
            for subvol in self.clientSubvolList(withUUID=False):
                if heapq.nlargest(1, clientTsList)[0] in subvol:
                    logInfo("isLockfile(): Newest client subvolume is %s" % subvol)
                    return subvol

    def clientDeleteSubvol(self, subvolume):
        subvolume = os.path.basename(os.path.normpath(subvolume))
        p1 = Popen(["sudo", "btrfs", "subvol", "delete", "%s" % subvolume], stdout=PIPE)
        out, err = p1.communicate()
        logDebug("subprocess output: %s \nsubprocess error: %s" % (out, err))
        if p1.returncode != 0:
            logError("Subprocess returncode != 0 for clientDeleteSuvol() method. Exiting Backup.")
            sendmail("error", "Bytterfs", "Subprocess returncode != 0 for clientDeleteSuvol() method. Exiting Backup")
        logWarning("Deleted %s" % subvolume)

    def clientDeleteOlderSnapshots(self):
        clientSubvolList = self.clientSubvolList(withUUID=False)
        logDebug("Received this clientSubvolList: %s" % clientSubvolList)
        tsList = self.subvolSplitTsList(clientSubvolList)
        smallestTsList = heapq.nsmallest(len(tsList)-1, tsList)
        logWarning("Going to delete following clientSubvols: %s \n If latter list is empty, then there is only one"
                   " or none client subvolume." % smallestTsList)
        for subvolTs in smallestTsList:
            process = Popen(["sudo", "btrfs", "subvol", "delete", "%s%s_%s" % (self.source, self.snapshotName,
                                                                               subvolTs)],
                            stdout=PIPE, stderr=PIPE)
            out, err = process.communicate()
            logDebug("subprocess output: %s \nsubprocess error: %s" % (out, err))
            if process.returncode != 0:
                logError("Error when deleting older snapshots on client. Exiting Backup.")
                sendmail("error", "Bytterfs", "Error when deleting older snapshots on client.")
                exit(0)
        logInfo("Delete older subvolume successfully.")
        clientLatestTs = heapq.nlargest(1, tsList)[0]  # heapq always returns a list, not a string.
        logDebug("clientLatestTs: %s" % clientLatestTs)
        return clientLatestTs  # Returning only timestamp, because that's sufficient for further usage.

    def clientSubvolList(self, withUUID):
        process = Popen(["sudo", "btrfs", "subvol", "list", "-o", "-r", "-u", self.source], stdout=PIPE, stderr=PIPE)
        out, err = process.communicate()
        splitRows = out.decode('latin-1').split("\n")
        splitRows = filter(None, splitRows)  # filters out empty list elements
        subvolList = []
        for row in splitRows:
            splitLine = row.split(" ")  # if the subvol path contains spaces, it'll break the code.
            subvolUUID = splitLine[8]
            subvolName = splitLine[10]
            if self.snapshotName in os.path.basename(os.path.normpath(subvolName)):   # Assuring to catch right subvol.
                if withUUID is True:
                    subvolList.append((subvolName, subvolUUID))
                else:
                    subvolList.append(subvolName)
        logDebug("Returned subvolList:  %s" % subvolList)
        return subvolList

    def clientCreateSnapshot(self):
        ts = int(time.time())
        newSnapshot = "%s%s_%s" %(self.source, self.snapshotName, ts)
        process = Popen(["sudo", "btrfs", "subvol", "snapshot", "-r", self.source, "%s" % (newSnapshot)],
                        stdout=PIPE,stderr=PIPE)
        out, err = process.communicate()
        if process.returncode != 0:
            logError("Error when creating readonly snapshot. Exiting Backup.")
            sendmail("error", "Bytterfs", "Error when creating readonly snapshot. Exiting Backup.")
            exit(0)
        return newSnapshot

    def destLatestSnapshot(self):
        destTsList = self.subvolSplitTsList(self.destSubvolList(withUUID=False))
        for subvol in self.destSubvolList(withUUID=False):
            if heapq.nlargest(1, destTsList)[0] in subvol:
                logInfo("isLockfile(): Newest dest subvolume is %s" % subvol)
                return subvol

    def destSubvolList(self, withUUID):
        p1 = Popen(self.sshArgs + ["sudo", "btrfs", "subvol", "list", "-o", "-R", self.destContainer], stdout=PIPE)
        out, err = p1.communicate()
        logDebug("subprocess output: %s \nsubprocess error: %s" % (out, err))
        if p1.returncode != 0:
            logError("Subprocess returncode != 0 for destSuvolList() method. Exiting Backup.")
            sendmail("error", "Bytterfs", "Subprocess returncode != 0 for destSuvolList() method. Exiting Backup")
            exit(0)
        splitRows = out.decode('latin-1').split("\n")
        splitRows = filter(None, splitRows)   # filters out empty list elements
        subvolList = []
        for row in splitRows:
            splitLine = row.split(" ")   # if the subvol path contains spaces, it'll break the code.
            subvolUUID = splitLine[8]
            subvolName = splitLine[10]
            if self.snapshotName in subvolName:   # Making sure to catch the right snapshots
                if withUUID is True:
                    subvolList.append((subvolName.rstrip("\r"), subvolUUID))
                else:
                    subvolList.append(subvolName.rstrip("\r"))
        logDebug("subvolList: %s" % subvolList)
        return subvolList

    def destNewestSnapshot(self):
        subvolSplitTsList = self.subvolSplitTsList(self.destSubvolList(withUUID=False))
        logDebug("subvolSplitTsList is: %s" % subvolSplitTsList)
        destNewestTs = subvolSplitTsList[-1:][0]  # Which return value is sorted.
        logDebug("destNewestTs is: %s" % destNewestTs)
        return destNewestTs

    def destDeleteSubvol(self, subvolume):
        subvolume = os.path.basename(os.path.normpath(subvolume))
        p1 = Popen(self.sshArgs + ["sudo", "btrfs", "subvol", "delete", "%s%s" % (self.destContainer, subvolume)],
                   stdout=PIPE)
        out, err = p1.communicate()
        logDebug("subprocess output: %s \nsubprocess error: %s" % (out, err))
        if p1.returncode != 0:
            logError("Subprocess returncode != 0 for destDeleteSubvol() method. Exiting Backup.")
            sendmail("error", "Bytterfs", "Subprocess returncode != 0 for destDeleteSubvol() method. Exiting Backup")
            exit(0)
        logWarning("destDeleteSubvol: Deleted: %s" % subvolume)

    def destKeepSnapshots(self):
        ''' Makes sure, that only a maximum number of snapshots are kept on backup server. Runs after backup. '''
        keepList = self.keep.split(",")
        timeKeepTupelList = []
        seconds = None
        for element in keepList:
            match = re.search("([0-9]+)([m|w])=([0-9]+)", element)
            if match.group(2) == "w":
                seconds = int(match.group(1))*7*24*60*60
            elif match.group(2) == "m":
                seconds = int(match.group(1))*30*24*60*60
            else:
                logError("Syntax of keep parameter wrong. Valid parameters 'w' or 'm' not found.")
                sendmail("error", "bytterfs", "Syntax of keep parameter wrong. Valid parameters 'w' or 'm' not found.")
                exit(0)
            keep = match.group(3)
            timeKeepTupelList.append((seconds, keep))
        logDebug("timeKeepTupelList: %s" % timeKeepTupelList)
        destTsList = self.subvolSplitTsList(self.destSubvolList(withUUID=False))
        currentTs = time.time()
        tsKeepTupeldict = defaultdict(list)  # easier to append elements to key
        logDebug("tsList: %s" % destTsList)
        for ts in destTsList:
            for index, element in enumerate(timeKeepTupelList, start=0):
                deltaTs = currentTs - int(ts)
                seconds = element[0]
                if index == 0:
                    if deltaTs < int(seconds):
                        tsKeepTupeldict[seconds].append(ts)
                    continue
                if deltaTs > int(timeKeepTupelList[index - 1][0]) and deltaTs < int(seconds):
                    tsKeepTupeldict[seconds].append(ts)
        for sec, keep in timeKeepTupelList:
            for key in tsKeepTupeldict:
                if sec == key and len(tsKeepTupeldict[key]) > int(keep):
                    tsListToBeRemoved = list(evenSpread(tsKeepTupeldict[key], len(tsKeepTupeldict[key])-int(keep)))
                    for ts in tsListToBeRemoved:
                        logInfo("Deleting this snapshot: %s_%s" % (self.snapshotName, ts))
                        self.destDeleteSubvol("%s_%s" % (self.snapshotName, ts))
        return True

    def destHasContainer(self):
        p1 = Popen(self.sshArgs + ["sudo", "btrfs", "subvol", "list", "-o", self.destRootSubvol], stdout=PIPE)
        out, err = p1.communicate()
        logDebug("destContainer stripped path: %s" % self.destContainer.replace(self.destRootSubvol, "").rstrip("/"))
        if not self.destContainer.replace(self.destRootSubvol, "").rstrip("/") in out.decode("utf-8"):
            logError("Specified destination subvolume container does not seem to exist. Exiting.")
            sendmail("error", "Bytterfs", "Specified destination subvolume container does not seem to exist. Exiting.")
            exit(0)

    def destHasSnapshot(self, clientInfo):
        """Checks if Snapshot is also present on target dest by comparing UUID of snapshot to 'sent UUIDs' on dest."""
        destSubvolList = self.destSubvolList(withUUID=True)
        logDebug("clientInfo is: %s" % clientInfo)
        for destSubvol in destSubvolList:
            if "-" in clientInfo:
                logDebug("clientInfo seems to contain UUID.")
                clientUUID = clientInfo
                for subvol in destSubvolList:
                    if clientUUID in subvol[1]:
                        logInfo("Last Snapshot is both on dest and client. Beginning increm. backup with send -p.")
                        return True
            elif is_number(clientInfo):
                logDebug("clientInfo seems to be a number (timestamp).")
                ts = clientInfo
                for subvol in destSubvolList:
                    logDebug("subvol in destSubVolList: %s\nChecking if ts %s in subvol. type(ts): %s"
                             % (subvol, ts, type(ts)))
                    if ts in subvol[0]:
                        logInfo("Last Snapshot is both on dest and client. Beginning increm. backup with send -p.")
                        return True
        logError("Last Snapshot is not on dest. Backup will continue and send missing snapshot "
                 "without `btrfs send -p` switch.")
        return False

    def run(self):
        """Performs backup run."""
        logInfo("Source entered: %s" % self.source)
        logInfo("destContainer entered: %s" % self.destContainer)
        logInfo('Preparing environment')
        self.destHasContainer()
        self.isLockfile()
        self.destKeepSnapshots()
        logInfo('initiateBackup()')
        self.initiateBackup()

#### Initializing Logger
logger = logging.getLogger()
# Add ColoredConsoleHandler
logger.addHandler(ColoredConsoleHandler())  # logger.addHandler(logging.StreamHandler(sys.stdout))
# Add SysLogHandler
log_syslog_handler = logging.handlers.SysLogHandler('/dev/log')  # /dev/log is the socket to log to syslog
log_syslog_handler.setFormatter(logging.Formatter(app_name + '[%(process)d] %(message)s'))
logger.addHandler(log_syslog_handler)
logger.info('%s v%s by %s' % (app_name, __version__, __author__))

try:
    parser = ArgumentParser(description="bytterfs. Incremental Backup helper for btrfs send/receive over SSH. "
                                         "Make sure that the SSH user has added following sudo rights in /etc/sudoers: "
                                         "..... ..... ..... username ALL=NOPASSWD: /usr/bin/btrfs subvol delete* ..... "
                                         "..... ..... ..... username ALL=NOPASSWD: /usr/bin/btrfs subvol list* ..... "
                                         "..... ...... "
                                         "This way you can run latter commands with sudo and don't have to type in the "
                                         "password. This is more secure, than connecting with SSH as root to the "
                                         "destination server. Also make sure that you have already created a subvolume"
                                         "on the backup destination which holds all your backup for the specific "
                                         "source.")
    parser.add_argument('snapshotName', type=str, help="Name of snapshot. A timestamp will then be suffixed to it. "
                                                       "E.g.: rootfs_1418415962.")
    parser.add_argument('source', type=checkPath, help='Source subvolume to backup. Local path or SSH url.')
    parser.add_argument('destRootSubvol', type=checkPath,
                        help="Destination root subvolume. This parameter is required to verify, that the specified "
                             "destinationContainer is existent on the destination root subvolume.")
    parser.add_argument('destContainer', type=checkPath, help="Destination container subvolume path, where snapshots "
                                                              "are send to.")
    parser.add_argument('sshHost', type=str, help='E.g.: user@192.168.1.100.')
    parser.add_argument('-p', '--sshPort', type=str, help='SSH Port.', required=True)
    parser.add_argument('-vv', '--debug', action='store_true', help='Log level: debug', required=False)
    parser.add_argument('-v', '--info', action='store_true', help='Log level: info', required=False)
    parser.add_argument('-i', '--sshKey', type=str, help='Path to your private key for your SSH user.', required=True)
    parser.add_argument('-dk', '--destKeep', type=checkTimespan,
                        help="Maximum number of destination snapshots to keep for a specific amount of time. Syntax "
                             "example: 5w=6,4m=3,6m=2,12m=3. Which means that at maximum 6 snapshots will be kept of "
                             "the last 5 weeks, maximum 3 snapshots will be kept within the time span of 5 weeks and "
                             "4 month, maximum 2 snapshots wil be kept from the time span of 4 months until 6 months "
                             "and maximum 3 snapshots will be kept from the time span of 6 until 12 months. Only w for "
                             "weeks and m for months is accepted syntax. Abstract: <time span>[w|m]= <number of snapsho"
                             "ts>optional(<comma as delimiter>)... Notice that the next specified time span has to be "
                             "greater than the previous, else the parameter will yield an error.", required=True)
    args = parser.parse_args()
    # Add fileHandler
    logPath = "%s%s" % ("/var/log/", app_name)
    mkdir_p(logPath)
    logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]  %(message)s")
    fileHandler = logging.FileHandler("{0}/{1}.log".format(logPath, args.snapshotName))  # {0}{1} used with format(logPath,...)
    fileHandler.setFormatter(logFormatter)
    logger.addHandler(fileHandler)
    if args.debug:
        logger.setLevel(logging.DEBUG)
    elif args.info:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.ERROR)
    bytterfs = Bytterfs(args.snapshotName, args.source, args.destRootSubvol, args.destContainer,
                        args.destKeep, args.sshHost, args.sshPort, args.sshKey)
    bytterfs.run()
except SystemExit as e:
    if e.code != 0:
        raise
except:
    logger.error('ERROR {0} {1}'.format(sys.exc_info(), traceback.extract_tb(sys.exc_info()[2])))
    raise
exit(0)
