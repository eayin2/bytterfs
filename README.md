bytterfs
========
Bytterfs - shortel for Backup python Butterfs - is a backup script using btrfs send/receive features to incrementally backup
via SSH to a remote server.

####  Usage description
```
usage: bytterfs.py [-h] -p SSHPORT -i SSHKEY -dk DESTKEEP
                   snapshotName source destRootSubvol destContainer sshHost

bytterfs. Incremental Backup helper for btrfs send/receive over SSH. Make sure
that the SSH user has added following sudo rights in /etc/sudoers

username ALL=NOPASSWD: /usr/bin/btrfs subvol delete*
username ALL=NOPASSWD: /usr/bin/btrfs subvol list*

This way you can run latter commands with sudo and don't have to type in the
password. This is more secure, than connecting with SSH as root to the
destination server. Also make sure that you have already created a subvolume on
the backup destination which holds all your backup for the specific source.

positional arguments:
  snapshotName          Name of snapshot. A timestamp will then be suffixed to
                        it. E.g.: rootfs_1418415962.
  source                Source subvolume to backup. Local path or SSH url.
  destRootSubvol        Destination root subvolume. This parameter is required
                        to verify, that the specified destinationContainer is
                        existent on the destination root subvolume.
  destContainer         Destination container subvolume path, where snapshots
                        are send to.
  sshHost               E.g.: user@192.168.1.100.

optional arguments:
  -h, --help            show this help message and exit
  -p SSHPORT, --sshPort SSHPORT
                        SSH Port.
  -i SSHKEY, --sshKey SSHKEY
                        Path to your private key for your SSH user.
  -dk DESTKEEP, --destKeep DESTKEEP
                        Maximum number of destination snapshots to keep for a
                        specific amount of time. Syntax example:
                        5w=6,4m=3,6m=2,12m=3. Which means that at maximum 6
                        snapshots will be kept of the last 5 weeks, maximum 3  
                        snapshots will be kept within the time span of 5 weeks
                        and 4 month, maximum 2 snapshots wil be kept from the
                        time span of 4 months until 6 months and maximum 3
                        snapshots will be kept from the time span of 6 until
                        12 months. Only w for weeks and m for months is<br>
                        accepted syntax. Abstract: <time span>[w|m]= <number
                        of snapshots>optional(<comma as delimiter>)... Notice
                        that the next specified time span has to be greater
                        than the previous, else the parameter will yield an
                        error.
```          

#### Features:
- Rotating snapshots on backup destination
- syslog Logging
- lockfile for interrupted backups and trying to fix interrupted backups next run
- mail notification, requires gymail. see: (https://github.com/eayin2/gymail) <br>

#### Preparations:<br>
Before using this backup script you should prepare following things:<br>
- Create a subvolume on the backup destination, which will hold/contain the <br>
   Backups/Snapshots. E.g. /mnt/3tb/@rootfs/  which will then hold e.g. backups as <br>
   such: /mnt/3tb/@rootfs/@rootfs_1418932376   <br>
- If you don't use root to connect to your backup destination (which is recommended,  <br>
   because if you many clients accessing your backup destination you would increase  <br>
   the risk for a rogue client), then you have to add: <br>
   username ALL=NOPASSWD: /usr/bin/btrfs subvol delete*<br>
   username ALL=NOPASSWD: /usr/bin/btrfs subvol list*<br>
   to /etc/sudoers<br>

#### Requirements: <br>
- btrfs-utils
- qymail script (https://github.com/eayin2/gymail) 
  --> Notice: Create a symlink to /usr/local/bin/sendmail.py for the script. `ln -s /path/script /usr/local/bin/sendmail.py`
  (If you dont want to use it then just remove all sendmail lines)
- python3<br>

#### Notice:<br>
- This script only supports btrfs send/receive operations from a local to an SSH remote machine.<br>
- Only one snapshot is kept on the client and only the destination will hold multiple snapshots<br>
  (see parameter syntax infos above). You can modify/extend this script to store more than one<br>
  snapshot on the client. I did not do it, because I use an SSD on my client and don't want to<br>
  store multiple snapshots on my client.<br>

#### Example Usage: <br>
`sudo ./bytterfs.py @home /home/ /mnt/3tb/ /mnt/3tb/@home/ user@192.168.1.100 -p 22 -i /home/user/.ssh/id_rsa -dk 1m=6,4m=6,10=5`
<br>
