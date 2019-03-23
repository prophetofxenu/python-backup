#TODO remove old backups

from argparse import ArgumentParser
import datetime
import hashlib
import logging
import os
import re
from shutil import copy2 as copy, rmtree, make_archive
import sys
import toml
from zipfile import ZipFile

conf_path: str = "./conf.toml"
records_path: str = "./records.toml"
stats_path: str = "./stats.toml"
tmp_log_path: str = "/tmp/python-backup.log"

init_time: str = datetime.datetime.now().strftime("%m-%d-%Y %a %H-%M-%S")
log_destination: str = "./logs/" + init_time + ".log"

def init_logger():
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))

    file = logging.FileHandler(tmp_log_path)
    file.setLevel(logging.INFO)
    file.setFormatter(logging.Formatter("[%(asctime)s %(levelname)s] %(message)s"))

    logging.basicConfig(handlers=[console, file])

    global logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

def write_log():
    copy(tmp_log_path, log_destination)
    os.remove(tmp_log_path)

def gen_config_file(path: str):
    if os.path.exists(path):
        return

    conf_file: str = """# This is the config file for backup.py
# Formatting is TOML: https://github.com/toml-lang/toml

# Add all source directories to backup.
source-directories = [

]

# Add destination at which to store backups
destination = ""

# Regular expressions to test items against. If a match occurs, the file will be ignored. Remember to properly escape special characters.
ignored = [

]

# Set total number of differential backups to perform before the next full backup
differential-backups = 6

# Use MD5 hashing instead of mtime to check if a file has been changed. MD5 is more accurate, but heavily increases the amount of time that the backup takes.
use-md5 = false"""

    with open(path, "w") as f:
        f.write(conf_file)

    return toml.loads(conf_file)

def verify_conf(conf: dict):
    valid: bool = True
    keys: set = conf.keys()

    if "source-directories" not in keys or not isinstance(conf["source-directories"], list) or len(conf["source-directories"]) == 0:
        logger.critical("Invalid source-directories entry in " + conf_path)
        valid = False
    if "destination" not in keys or len(conf["destination"]) == 0:
        logger.critical("Invalid destination entry in " + conf_path)
        valid = False
    if "ignored" not in keys or not isinstance(conf["ignored"], list):
        logger.critical("Invalid ignored entry in " + conf_path)
        valid = False
    if "differential-backups" not in keys or conf["differential-backups"] < 0:
        logger.critical("Invalid differential-backups entry in " + conf_path)
        valid = False
    # if "current-differential-backups" not in keys or conf["current-differential-backups"] < 0:
    #     logger.critical("Invalid current-differential-backups entry in " + conf_path)
    #     valid = False
    # if "last-full-timestamp" not in keys:
    #     logger.critical("Invalid last-full-timestamp entry in " + conf_path)
    #     valid = False
    # if "last-differential-timestamp" not in keys:
    #     logger.critical("Invalid last-differential-timestamp entry in " + conf_path)
    #     valid = False
    if "use-md5" not in keys:
        logger.critical("use-md5 key missing from config")
        valid = False
    else:
        if os.path.exists(records_path):
            records: dict = toml.load(records_path)
            if conf["use-md5"]:
                if not bool(re.search("[A-z]", records[list(records.keys())[0]])):
                    logger.critical("config says to use MD5, but record file is storing mtime")
                    valid = False
            else:
                if bool(re.search("[A-z]", records[list(records.keys())[0]])):
                    logger.critical("config says to use mtime, but record file is storing MD5")
                    valid = False
                    
    return valid

def gen_stats_file(path: str):
    stats: dict = {}
    stats["total_uncompressed_filesize"]: int = 0
    stats["total_files"]: int = 0
    stats["total_dirs"]: int = 0

    stats["full_backups"]: int = 0
    stats["diff_backups"]: int = 0

    stats["last_backup_type"]: int = 2
    stats["current-differential-backups"]: int = 0

    stats["last-full-timestamp"]: int = 0
    stats["last-diff-timestamp"]: int = 0

    with open(path, "w") as f:
        toml.dump(stats, f)

    return stats

def print_stats(stats: dict, conf: dict):
    print("backup.py statistics\n")
    
    print("Total Size of Uncompressed Files: " + hr_size(stats["total_uncompressed_filesize"]))
    print("Total Files Backedup: " + str(stats["total_files"]))
    print("Total Directories Backedup: " + str(stats["total_dirs"]))
    print("Total Items Backedup: " + str(stats["total_files"] + stats["total_dirs"]) + "\n")

    print("Total Full Backups: " + str(stats["full_backups"]))
    print("Total Differential Backups: " + str(stats["diff_backups"]))
    print("Total Backups: " + str(stats["full_backups"] + stats["diff_backups"]) + "\n")

    backup_type: int = stats["last_backup_type"]
    if backup_type == 0:
        print("Last Backup Type: Full")
    elif backup_type == 1:
        print("Last Backup Type: Differential")
    else:
        print("No backup has been run yet")
    
    print("Diff backups left before next Full backup: " + str(conf["differential-backups"] - stats["current-differential-backups"]))

    last_full: str = datetime.datetime.fromtimestamp(stats["last-full-timestamp"]).strftime("%m/%d/%Y %a %H:%M:%S")
    last_diff: str = datetime.datetime.fromtimestamp(stats["last-diff-timestamp"]).strftime("%m/%d/%Y %a %H:%M:%S")
    print("Last Full Backup: " + last_full)
    print("Last Diff Backup: " + last_diff)

def write_toml(d: dict, path: str):
    with open(path, "w") as f:
        toml.dump(d, f)

def confirm(question: str, default_yes: bool=True, default_no: bool=False):
    if default_yes:
        response: str = input(question + " (Y/n) ")
    elif default_no:
        response: str = input(question + " (y/N) ")
    else:
        response: str = input(question + " (y/n) ")
    if response == "":
        if default_yes:
            return True
        if default_no:
            return False

    response = response.lower()
    if response == "y":
        return True
    if response == "n":
        return False

    print("Invalid response")
    return confirm(question, default_yes, default_no)

def item_from_path(path: str):
    if path[-1] == '/':
        return path.split("/")[-2]
    return path.split("/")[-1]

def hr_size(size: int):
    if size // 1000 < 1:
        return str(size) + "B"
    if size // 1000000 < 1:
        return str(size / 1000) + "KB"
    if size // 1000000000 < 1:
        return str(size / 1000000) + "MB"
    if size // 1000000000000 < 1:
        return str(size / 1000000000) + "GB"

def item_size(path: str):
    size: float = float(os.stat(path).st_size)
    return hr_size(size)

def is_ignored(conf: dict, item: str):
    for pattern in conf["ignored"]:
        if bool(re.match(pattern, item)):
            return True
    return False

def full_backup(conf: dict, compress=True):
    working_dir: str = os.path.abspath(os.curdir)
    now: str = datetime.datetime.now().strftime("%m-%d-%Y_%a_%H-%M-%S")
    records: dict = {}
    destination_path: str = conf["destination"] + "_Full_" + now

    backup_record: dict = {}
    backup_record["total_filesize"]: int = 0
    backup_record["total_files"]: int = 0
    backup_record["total_directories"]: int = 0

    try:
        logger.info("Creating destination path at " + destination_path)
        os.mkdir(destination_path)
    except FileExistsError:
        logger.warning("Destination path already exists")
        if confirm("The destination folder already exists at %s. Remove?" %destination_path, False, True): 
            logger.debug("User chose to remove the existing directory at destination path")
            rmtree(destination_path)
            os.mkdir(destination_path)
        else:
            logger.critical("User chose to leave the existing directory")
            write_log()
            exit(1)
    for path in conf["source-directories"]:
        logger.info("Creating destination directory for " + path)
        os.mkdir(destination_path + "/" + item_from_path(path))

        logger.info("Destination created. Backing up " + path)
        dir_record: dict = backup_dir(True, path, destination_path + "/" + item_from_path(path), records, conf["use-md5"])

        backup_record["total_filesize"] += dir_record["total_filesize"]
        backup_record["total_files"] += dir_record["total_files"]
        backup_record["total_directories"] += dir_record["total_directories"]
    
    os.chdir(destination_path)
    if compress:
        try:
            logger.info("Finished copying source directories. Archiving")
            make_archive("Full_" + now, "zip", destination_path)
        except ValueError as e:
            logger.error("Error occured during creation of archive: " + str(e))
        logger.info("Archive created. Removing working files")
        for file in os.listdir(destination_path):
            if os.path.isdir(file):
                logger.debug("Removing " + file)
                rmtree(destination_path + "/" + file)
        with ZipFile("Full_" + now + ".zip") as z:
            logger.info("Full backup completed. Backed up %d items with a compressed size of %s" %(len(z.infolist()) - 2, item_size(destination_path + "/Full_" + now + ".zip")))
    else:
        items: int = backup_record["total_directories"] + backup_record["total_files"]
        logger.info("Full backup completed. Backed up %d items with a total size of %s" %(items, hr_size(backup_record["total_filesize"])))

    os.chdir(working_dir)
    write_toml(records, records_path)
    logger.debug("Record file written to " + records_path)
    backup_record["log_path"]: str = "%s/%s.log" %(destination_path, now)
    
    return backup_record

def differential_backup(conf: dict, compress=True):
    working_dir: str = os.path.abspath(os.curdir)
    now: str = datetime.datetime.now().strftime("%m-%d-%Y_%a_%H-%M-%S")
    records: dict = toml.load(records_path)
    logger.debug("Loaded records file at " + records_path)
    destination_path: str = conf["destination"] + "_Differential_" + now

    backup_record: dict = {}
    backup_record["total_filesize"]: int = 0
    backup_record["total_files"]: int = 0
    backup_record["total_directories"]: int = 0

    try:
        logger.info("Creating destination path at " + destination_path)
        os.mkdir(destination_path)
    except FileExistsError:
        if confirm("The destination folder already exists at %s. Remove?" %destination_path, False, True): 
            logger.debug("User chose to remove the existing directory at destination path")
            rmtree(destination_path)
            os.mkdir(destination_path)
        else:
            logger.critical("User chose to leave the existing directory")
            exit(1)

    for path in conf["source-directories"]:
        logger.info("Creating destination directory for " + path)
        os.mkdir(destination_path + "/" + item_from_path(path))
        logger.debug("Destination created. Backing up " + path)
        dir_record: dict = backup_dir(False, path, destination_path + "/" + item_from_path(path), records, conf["use-md5"])

        backup_record["total_filesize"] += dir_record["total_filesize"]
        backup_record["total_files"] += dir_record["total_files"]
        backup_record["total_directories"] += dir_record["total_directories"]

    os.chdir(destination_path)
    if compress:
        try:
            logger.info("Finished copying source directories. Archiving")
            make_archive("Differential_" + now, "zip", destination_path)
        except ValueError as e:
            logger.error("Error occured during creation of archive: " + str(e))

        logger.info("Archive created. Removing working files")
        for file in os.listdir(destination_path):
            if os.path.isdir(file):
                logger.debug("Removing " + file)
                rmtree(destination_path + "/" + file)

        with ZipFile("Differential_" + now + ".zip") as z:
            logger.info("Differential backup completed. Backed up %d items with a compressed size of %s." %(len(z.infolist()), item_size(destination_path + "/Differential_" + now + ".zip")))
        os.chdir(working_dir)
    else:
        items: int = backup_record["total_files"] + backup_record["total_directories"]
        logger.info("Differential backup completed. Backed up %d items with a total size of %d" %(items, hr_size(backup_record["total_filesize"])))

    backup_record["log_path"]: str = "%s/%s.log" %(destination_path, now)
    return backup_record
    
def backup_dir(full_backup: bool, path: str, destination: str, records: dict, use_md5: bool):
    previous_path: str = os.path.abspath(os.curdir)
    os.chdir(path)

    backup_record: dict = {}
    backup_record["total_filesize"]: int = 0
    backup_record["total_files"]: int = 0
    backup_record["total_directories"]: int = 0

    for item in os.listdir():
        if is_ignored(conf, item):
            logger.info("Skipping item " + item)
            continue

        logger.debug("Backing up item " + item)

        item_path: str = os.path.abspath(path + "/" + item)
        item_destination_path: str = os.path.abspath(destination + "/" + item)
        if os.path.isdir(item_path):
            logger.debug(item + " is a directory, descending")
            os.mkdir(item_destination_path)
            prev: dict = backup_dir(full_backup, item_path, item_destination_path, records, use_md5)

            if not full_backup and len(os.listdir(item_destination_path)) == 0: #delete the directory if nothing was backed up
                logger.debug("Nothing in %s needed to be backed up. Removing source directory" %item_path)
                os.rmdir(item_destination_path)
            else:
                backup_record["total_filesize"] += prev["total_filesize"]
                backup_record["total_files"] += prev["total-files"]
                backup_record["total_directories"] += prev["total_directories"] + 1

        else:
            if use_md5:
                logger.debug("Checking file %s using MD5" %item_path)
                compare: str = hashlib.md5(open(item_path, "rb").read()).hexdigest()
            else:
                logger.debug("Checking file %s using mtime" %item_path)
                compare: str = str(os.path.getmtime(item_path))
            if full_backup or (item_path not in records.keys() or records[item_path] != compare):
                if full_backup:
                    records[item_path] = compare
                    logger.debug("Updated %s in records: %s" %(item_path, compare))

                copy(item_path, item_destination_path)
                logger.info("Backed up " + item_path)

                backup_record["total_files"] += 1
                backup_record["total_filesize"] += os.stat(item_path).st_size

    os.chdir(previous_path)
    return backup_record

if __name__ == "__main__":
    parser = ArgumentParser()
    
    # flags
    parser.add_argument('-f', '--full', help='Run a full backup', action='store_true')
    parser.add_argument('-d', '--differential', help='Run a differential backup', action='store_true')
    parser.add_argument('--no-increment', help='Don\'t increase the number of differential backups run', action='store_true')
    parser.add_argument('--reset-increments', help='Reset the number of differential backups run to zero and exit', action='store_true')
    parser.add_argument('--no-compress', help='Don\'t zip the backup', action='store_true')
    parser.add_argument('-s', '--stats', help='Print statistics and exit', action='store_true')

    # optional args
    parser.add_argument('-config-path', help='Custom path to config file', type=str)
    parser.add_argument('-log-path', help='Custom path to create log file at', type=str)
    parser.add_argument('-records-path', help='Custom path to read/write records file', type=str)
    parser.add_argument('-stats-path', help='Custom path to read/write stats file', type=str)

    args = parser.parse_args()

    init_logger()
    logger.debug("Program started")
    if(not os.path.exists(conf_path)):
        logger.debug("Config file at %s does not exist" %conf_path)
        gen_config_file(conf_path)
        logger.debug("Generated config file at " + conf_path)
        print("config file created at %s. Please edit it before running this program again." %os.path.abspath(conf_path))
        if not os.path.exists(tmp_log_path):
            os.mkdir("logs")
        write_log()
    else:
        conf: dict = toml.load(conf_path)
        if not verify_conf(conf):
            exit(1)

        if not os.path.exists(stats_path):
            stats: dict = gen_stats_file(stats_path)
        else:
            stats: dict = toml.load(stats_path)

        if args.reset_increments:
            conf["current-differential-backups"] = 0
            logger.info("Reset current differential backups to zero")
            write_toml(conf, conf_path)
            os.remove(tmp_log_path)
            exit(0)

        if args.stats:
            print_stats(stats, conf)
            exit(0)

        if stats["last-full-timestamp"] == 0 or stats["current-differential-backups"] >= conf["differential-backups"]:
            backup_type: int = 0
        else:
            backup_type: int = 1
        if not args.full and not args.differential:
            if backup_type == 0:
                response: bool = confirm("The next backup is set to be a full backup. Proceed?")
                if not response:
                    if confirm("Perform a differential backup instead?", default_yes=False, default_no=True):
                        backup_type = 1
                    else:
                        exit(0)

            else:
                response: bool = confirm("The next backup is set to be a differential backup. Proceed?")
                if not response:
                    if confirm("Perform a full backup instead?", default_yes=False, default_no=True):
                        backup_type = 0
                    else:
                        exit(0)

        if (backup_type == 0 and not args.differential) or args.full:
            logger.info("Started full backup")

            backup_record: dict = full_backup(conf, compress=not args.no_compress)
            log_destination = backup_record["log_path"]

            now: datetime = datetime.datetime.now()

            conf["current-differential-backups"] = 0
            logger.debug("Reset current-differential-backups")

            stats["total_uncompressed_filesize"] += backup_record["total_filesize"]
            stats["total_files"] += backup_record["total_files"]
            stats["total_dirs"] += backup_record["total_directories"]

            stats["last_backup_type"] = 0
            stats["full_backups"] += 1
            stats["last-full-timestamp"] = now.timestamp()

            logger.debug("Updated stats")

        else:
            if not os.path.exists(records_path):
                logger.critical("Record file not found; has a full backup been run yet?")
                exit(1)

            backup_record: dict = differential_backup(conf, compress=not args.no_compress)
            log_destination = backup_record["log_path"]

            if not args.no_increment:
                stats["current-differential-backups"] += 1

            now: datetime = datetime.datetime.now()

            stats["total_uncompressed_filesize"] += backup_record["total_filesize"]
            stats["total_files"] += backup_record["total_files"]
            stats["total_dirs"] += backup_record["total_directories"]

            stats["last_backup-type"] = 1
            stats["diff_backups"] += 1
            stats["current-differential-backups"]
            stats["last-diff-timestamp"] = now.timestamp()

        write_toml(stats, stats_path)
        logger.debug("Wrote stats file at " + stats_path)
        write_log()