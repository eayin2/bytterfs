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

from math import ceil
from subprocess import Popen, PIPE
from argparse import ArgumentParser, ArgumentTypeError
from collections import defaultdict

app_name = os.path.splitext(os.path.basename(__file__))[0]

#### Functions
def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def evenSpread(sequence, num):
    length = float(len(sequence))
    for i in range(num):
        yield sequence[int(ceil(i * length / num))]

def sendmail(event, subject, message):
    p = Popen(["/usr/local/bin/sendmail.py", "-e", event, "-s", subject, "-m", message], stdout=PIPE, stderr=PIPE)
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
        #match = re.search("([0-9]+)([m|w])",element)
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

    def __init__(self, logger, snapshotName, source, destRootSubvol, destContainer, keep, sshHost, sshPort, sshKey):
        self.logger = logger
        self.snapshotName = snapshotName
        self.source = source
        self.destContainer = destContainer
        self.destRootSubvol = destRootSubvol
        self.keep = keep
        self.sshHost = sshHost
        self.sshPort = sshPort
        self.sshKey = sshKey
        self.lockfile = "%s%s" %(self.source,"bytterfs.lock")

    def inc(self, newSnapshot, latestSnapshot):
        touch(self.lockfile)
        p1 = Popen(["sudo","btrfs", "send", "-p", "%s%s" %(self.source, latestSnapshot),
                    "%s%s" %(self.source, newSnapshot)],stdout=PIPE)
        p2 = Popen(["ssh", "-i", self.sshKey, "-p", self.sshPort, self.sshHost,
                    "sudo", "btrfs", "receive", self.destContainer],stdin=p1.stdout,stdout=PIPE)
        p1.stdout.close()
        out,err = p2.communicate()
        if p2.returncode != 0:
            self.logger.error("Error when doing incremental backup. Sending Mail and exiting. Output:%s Error:\
                              %s" %(out,err))
            sendmail("error", "Bytterfs","Error when doing incremental backup. Output:%s Error: %s" %(out,err))
            exit(0)
        print(out,err)
        os.remove(self.lockfile)

    def full(self, snapshot):
        touch(self.lockfile)
        p1 = Popen(["sudo","btrfs", "send",  "%s%s" %(self.source, snapshot)],stdout=PIPE)
        p2 = Popen(["ssh", "-i", self.sshKey, "-p", self.sshPort, self.sshHost,
                    "sudo", "btrfs", "receive", self.destContainer],stdin=p1.stdout,stdout=PIPE)
        p1.stdout.close()
        out, err = p2.communicate()
        if p2.returncode != 0:
            self.logger.error("Error when doing full backup. Sending Mail and exiting. Output:%s Error: %s" %(out,err))
            sendmail("error", "Bytterfs","Error when doing full backup. Output:%s Error: %s" %(out,err))
            exit(0)
        print(out, err)
        os.remove(self.lockfile)

    def subvolListSplitTs(self, subvolList):
        tsList = []
        for subvol in subvolList:
            try:
                tsList.append(subvol[0].split("_")[1])
            except:
                self.logger.error("There's a snapshot that has a wrong naming syntax. Exiting backup and sending mail.")
                sendmail("error", "Bytterfs","There's a snapshot that has a wrong naming syntax. Exiting backup.")
        return sorted(tsList)

    def isLockfile(self):
        if os.path.isfile(self.isLockfile()) is True:
            self.logger.info("No lockfile found. Seems last backup was not interrupted. Continuing.")
            pass
        else:
            self.logger.error("Lockfile found. Last backup was interrupted. Sending mail, checking if snapshot is \
                              present on destination and client. If it is present on both, then destination snapshot \
                              gets deleted and retransfered, if it is only on the client, then it gets just \
                              retransfered, if it is not on the client, but on the server a new roSnapshot will be \
                              created and the snapshot on the destination will be deleted and if it is on neither, then\
                              just a new roSnapshot will be created and transfered.")
            sendmail("error", "Bytterfs","Lockfile found. Deleting possible left over on destination and continuing \
                                         with backup. See local syslog for more details.")
            clientSubvolList = self.clientSubvolList()
            clientTsList = self.subvolListSplitTs(clientSubvolList)
            destTsList = self.subvolListSplitTs(self.destRootSubvol())
            destLatestSnapshot = None
            for subvol in self.destRootSubvol():
                if heapq.nlargest(1, destTsList) in subvol:
                    destLatestSnapshot = subvol
            if destLatestSnapshot is None:
                self.logger.error("No Snapshots found on destination. Something is wrong. Exiting and sending mail.")
                sendmail("error", "Bytterfs","No Snapshots found on destination. Something is wrong.")
                exit(0)
            if len(clientSubvolList) == 0:
                self.logger.info("isLockfile(): Found no roSnapshots on client.")
                self.destDeleteSubvol(destLatestSnapshot)
                self.full(self.clientCreateSnapshot())
            elif len(clientSubvolList) == 1:
                self.logger.info("isLockfile(): Found one roSnapshots on client.")
                if self.destHasSnapshot(clientTsList[0]):
                    self.destDeleteSubvol(destLatestSnapshot)
                    self.full(clientSubvolList[0])
                else:
                    self.full(clientSubvolList[0])
            elif len(clientSubvolList) > 1:
                self.logger.info("isLockfile(): Found more than one roSnapshots on client.")
                for i in range(len(clientSubvolList)):
                    newestSubvolTs = heapq.nlargest(i, clientTsList)
                    if self.destHasSnapshot(newestSubvolTs[i-1]):
                        self.destDeleteSubvol(newestSubvolTs[i-1])
                        self.full(newestSubvolTs[i-1])
                        break
                self.full(self.clientCreateSnapshot())

    def initiateBackup(self):
        subvolList = self.clientSubvolList()
        if len(subvolList) == 0:
            self.logger.error("Found no readonly snapshot on the client. Sending mail. Ignore this error, if you run \
                              bytterfs the first time.")
            sendmail("error", "Bytterfs","Found no readonly snapshot on client. Ignore this error, if you run bytterfs\
                     the first time.")
            newroSnapshot = self.clientCreateSnapshot()
            self.full(newroSnapshot)
        elif len(subvolList) == 1:
            self.logger.info("Found one matching readonly snapshot.")
            if self.destHasSnapshot(subvolList[1]) is True:
                newroSnapshot = self.clientCreateSnapshot()
                self.inc(newroSnapshot, subvolList[0])
            elif self.destHasSnapshot(subvolList[1]) is False:
                self.full(subvolList[0])
        elif len(subvolList) > 1:
            self.logger.error("Found more than one matching readonly snapshot, though there should only be one. Sending\
                              mail. Deleting older readonly snapshots and proceeding with backup.")
            latestRoSnapshot = self.clientDeleteOlderSnapshots(subvolList)
            newRoSnapshot = self.clientCreateSnapshot()
            sendmail("error", "Bytterfs","Found more than one readonly snapshot on client. Deleting older readonly \
                     snapshots, but still proceeding with backup.")
            self.inc(newRoSnapshot, latestRoSnapshot)

    def clientDeleteOlderSnapshots(self, subvolList):
        tsList = self.subvolListSplitTs(subvolList)
        smallestTsList = heapq.nsmallest(len(tsList)-1, tsList)
        for subvolTs in smallestTsList:
            process = Popen(["sudo", "btrfs", "subvolume", "delete", "%s_%s" %(self.snapshotName,subvolTs)],
                            stdout=PIPE,stderr=PIPE)
            out, err = process.communicate()
            if process.returncode != 0:
                self.logger.error("Error when deleting older snapshots on client. Exiting Backup.")
                sendmail("error", "Bytterfs","Error when deleting older snapshots on client.")
                exit(0)
        self.logger.info("Delete older subvolume successfully.")
        latestTs = heapq.nlargest(1, tsList)
        return "%s_%s" %(self.snapshotName, latestTs)

    def clientSubvolList(self):
        process = Popen(["sudo", "btrfs", "subvolume", "list", "-o", "-r", "-u", self.source],stdout=PIPE,stderr=PIPE)
        out, err = process.communicate()
        splitRows = out.decode('latin-1').split("\n")
        splitRows = filter(None, splitRows)  # filters out empty list elements
        subvolList = []
        for row in splitRows:
            splitLine = row.split(" ")  # if the subvol path contains spaces, it'll break the code.
            subvolUUID = splitLine[8]
            subvolName = splitLine[10]
            if self.snapshotName in subvolName: # Making sure to catch the right snapshots
                subvolList.append((subvolName, subvolUUID))
        return subvolList

    def clientCreateSnapshot(self):
        ts = int(time.time())
        newSnapshot = "%s%s_%s" %(self.source,self.snapshotName,ts)
        process = Popen(["btrfs", "subvolume", "snapshot", "-r", self.source, "%s" %(newSnapshot)],
                        stdout=PIPE,stderr=PIPE)
        out, err = process.communicate()
        if process.returncode != 0:
            self.logger.error("Error when creating readonly snapshot. Exiting Backup.")
            sendmail("error", "Bytterfs","Error when creating readonly snapshot. Exiting Backup.")
            exit(0)
        return newSnapshot

    def destSubvolList(self, uuid):
        p1 = Popen(["ssh", "-i", self.sshKey, "-p", self.sshPort, self.sshHost, "sudo", "btrfs", "subvol", "list",
          "-o", self.destContainer ],stdout=PIPE)
        out, err = p1.communicate()
        if p1.returncode != 0:
            self.logger.error("Subprocess returncode != 0 for destDeleteSuvol() method. Exiting Backup.")
            sendmail("error", "Bytterfs","Subprocess returncode != 0 for destDeleteSuvol() method. Exiting Backup")
        splitRows = out.decode('latin-1').split("\n")
        splitRows = filter(None, splitRows)   # filters out empty list elements
        subvolList = []
        for row in splitRows:
            splitLine = row.split(" ")   # if the subvol path contains spaces, it'll break the code.
            subvolUUID = splitLine[8]
            subvolName = splitLine[10]
            if self.snapshotName in subvolName:   # Making sure to catch the right snapshots
                if uuid is True:
                    subvolList.append((subvolName, subvolUUID))
                else:
                    subvolList.append(subvolName)
        return subvolList

    def destDeleteSubvol(self, subvolume):
        subvolume = os.path.basename(os.path.normpath(subvolume))
        p1 = Popen(["ssh", "-i", self.sshKey, "-p", self.sshPort, self.sshHost, "sudo", "btrfs", "subvol", "delete",
          "%s%s" %(subvolume)],stdout=PIPE)
        out, err = p1.communicate()
        if p1.returncode != 0:
            self.logger.error("Subprocess returncode != 0 for destDeleteSuvol() method. Exiting Backup.")
            sendmail("error", "Bytterfs","Subprocess returncode != 0 for destDeleteSuvol() method. Exiting Backup")

    def destKeepSnapshots(self):
        ''' Makes sure, that only a maximum number of snapshots are kept on backup server. Runs after backup. '''
        keepList = self.keep.split(",")
        secondsKeepTupelList = []
        seconds = None
        for element in keepList:
            match = re.search("([0-9]+)([m|w])=([0-9]+)",element)
            if match.group(2) == "w":
                seconds = int(match.group(1))*7*24*60*60
            elif match.group(2) == "m":
                seconds = int(match.group(1))*30*24*60*60
            else:
                self.logger.error("Syntax of keep parameter wrong. Valid parameters 'w' or 'm' not found.")
                sendmail("error", "bytterfs", "Syntax of keep parameter wrong. Valid parameters 'w' or 'm' not found.")
                exit(0)
            keep = match.group(3)
            secondsKeepTupelList.append((seconds, keep))
        tsList = self.subvolListSplitTs(self.destSubvolList(True))
        currentTs = time.time()
        tsKeepTupeldict = defaultdict(list)
        for ts in tsList:
            for index, sec, keep in enumerate(secondsKeepTupelList, start=0):
                deltaTs = currentTs - ts
                if index == 0:
                    if deltaTs < seconds:
                        tsKeepTupeldict[seconds].append(ts)
                        print("Deleting nothing")
                    continue
                if deltaTs > secondsKeepTupelList[index - 1] and deltaTs < seconds:
                    tsKeepTupeldict[seconds].append(ts)
        for sec, keep in secondsKeepTupelList:
            for key in tsKeepTupeldict:
                if sec == key and len(tsKeepTupeldict[key]) > keep:
                    tsListToBeRemoved = list(evenSpread(tsKeepTupeldict[key], len(tsKeepTupeldict[key])-keep))
                    for ts in tsListToBeRemoved:
                        self.destDeleteSubvol("%s_%s" % (self.snapshotName, ts))
        return True

    def destHasContainer(self):
        p1 = Popen(["ssh", "-i", self.sshKey, "-p", self.sshPort, self.sshHost, "sudo", "btrfs", "subvol", "list",
          "-o", self.destRootSubvol ],stdout=PIPE)
        out, err = p1.communicate()
        if not self.destContainer.replace(self.destRootSubvol,"") in out:
            self.logger.error("Specified destination subvolume container does not seem to exist. Exiting.")
            sendmail("error", "Bytterfs","Specified destination subvolume container does not seem to exist. Exiting.")
            exit(0)

    def destHasSnapshot(self, client_roSnapshotUUID):
        ''' Checks if roSnapshot is also present on target dest by comparing UUID of snapshot to 'sent UUIDs' on dest'''
        process = Popen(["ssh", self.sshhost, "sudo", "btrfs", "subvolume", "list", "-R", self.source,
                         "%s_%s" %(self.source, self.snapshotName)],stdout=PIPE,stderr=PIPE)
        out, err = process.communicate()
        if process.returncode != 0:
            self.logger.error("Error when checking, if server has parent snapshot. Exiting Backup.")
            sendmail("error", "Bytterfs","Error when creating readonly snapshot. Exiting Backup.")
        splitRows = out.decode('latin-1').split("\n")
        splitRows = filter(None, splitRows)
        server_sentSubvolList = []
        for row in splitRows:
            splitLine = row.split(" ")
            server_sentSubvolList.append(splitLine[8]) # list of UUIDs
        if client_roSnapshotUUID in server_sentSubvolList:
            self.logger.info("Last roSnapshot is both on server and client. Beginning incremental backup with send -p.")
            return True
        else:
            self.logger.error("Last roSnapshot is not on server. Sending Email, because this should not happen. Yet the\
                             backup will continue and send the missing snapshot without `btrfs send -p` switch.")
            return False

    def run(self):
        ''' Performs backup run '''
        self.logger.info(self.source)
        self.logger.info(self.destContainer)
        self.logger.info('Preparing environment')
        self.isLockfile()
        self.destHasContainer()
        self.source.prepare_environment()
        self.initiateBackup()
        # Clean out excess backups/snapshots
        self.destKeepSnapshots()
        self.clientDeleteOlderSnapshots(self.clientSubvolList())
        self.logger.info('Backup %s created successfully' % (self.snapshotName))

#### Initializing Logger
logger = logging.getLogger()
# configuring a stream handler (using stdout instead of the default stderr) and adding it to the root logger
logger.addHandler(logging.StreamHandler(sys.stdout))
log_syslog_handler = logging.handlers.SysLogHandler('/dev/log')  # /dev/log is the socket to log to syslog
log_syslog_handler.setFormatter(logging.Formatter(app_name + '[%(process)d] %(message)s'))
logger.addHandler(log_syslog_handler)
logger.setLevel(logging.INFO)
logger.info('%s v%s by %s' % (app_name, __version__, __author__))

try:
    parser = ArgumentParser(description="bytterfs. Incremental Backup helper for btrfs send/receive over SSH., \
                                         Make sure SSH user has rights in sudoers for sudo btrfs receive.")
    parser.add_argument('snapshotName', type=str, help='Name of snapshot. A timestamp will then be suffixed to it. E.g.\
                        rootfs_1418415962.')
    parser.add_argument('source', type=checkPath, help='Source subvolume to backup. Local path or SSH url.')
    parser.add_argument('destRootSubvol', type=checkPath, help='Destination root subvolume. This parameter is needed to\
                        verify, that the specified destinationContainer is existent on the destination root subvolume.')
    parser.add_argument('destContainer', type=checkPath, help='Destination container subvolume path, where snapshots \
                        are send to.')
    parser.add_argument('sshhost', type=str, help='E.g.: user@192.168.1.100.')
    parser.add_argument('-p', '--sshPort', type=str, help='SSH Port.')
    parser.add_argument('-i', '--sshKey', type=str, help='Path to your private key for your SSH user.')
    parser.add_argument('-dk', '--destKeep', type=checkTimespan, help='Maximum number of destination snapshots to keep \
                        for a specific amount of time. Syntax example: 5w=6,4m=3,6m=2,12m=3. Which means that at \
                        maximum 6 snapshots will be kept of the last 5 weeks, maximum 3 snapshots will be kept\
                        within the time span of 5 weeks and 4 month, maximum 2 snapshots wil be kept from the time span\
                        of 4 months until 6 months and maximum 3 snapshots will be kept from the time span of 6 until\
                        12 months. Only w for weeks and m for months is accepted syntax. Abstract: <time span>[w|m]=\
                        <number of snapshots>optional(<comma as delimiter>)... Notice that the next specified time \
                        span has to be greater than the previous, else the parameter will yield an error.')
    args = parser.parse_args()
    print(args.destination_max_snapshots)
    bytterfs = Bytterfs(logger,args.snapshotName, args.source, args.destRootSubvol, args.destContainer,
                        args.destKeep, args.sshhost, args.sshPort, args.sshKey)
    bytterfs.run()
except SystemExit as e:
    if e.code != 0:
        raise
except:
    logger.error('ERROR {0} {1}'.format(sys.exc_info(), traceback.extract_tb(sys.exc_info()[2])))
    raise
exit(0)
