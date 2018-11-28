#TODO verify that type of record stored is correct type (md5 or mtime)
#TODO add eval() conditions for running types of backups
#TODO add logging
#TODO remove old backups
#TODO fix comments in conf being deleted
#TODO add commandline arguments

import datetime
import hashlib
import os
import re
from shutil import copy2 as copy, rmtree, make_archive
import toml
from zipfile import ZipFile

conf_path: str = "./conf.toml"
records_path: str = "./records.toml"

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
use-md5 = false


# The below entries are for internal use by the program, and should typically not be altered

# The number of differential backups that have been performed since the last full backup
current-differential-backups = 0

# The date of the last full backup. Only the timestamp is actually used by the program
last-full = "never"
last-full-timestamp = 0.0

# The date of the last differential backup. Only the timestamp is actually used by the program
last-differential = "never"
last-differential-timestamp = 0.0"""
    with open(path, "w") as f:
        f.write(conf_file)
    return toml.loads(conf_file)

def verify_conf(conf: dict):
    valid: bool = True
    keys: set = conf.keys()
    if "source-directories" not in keys or not isinstance(conf["source-directories"], list) or len(conf["source-directories"]) == 0:
        print("Invalid source-directories entry in " + conf_path)
        valid = False
    if "destination" not in keys or len(conf["destination"]) == 0:
        print("Invalid destination entry in " + conf_path)
        valid = False
    if "ignored" not in keys or not isinstance(conf["ignored"], list):
        print("Invalid ignored entry in " + conf_path)
        valid = False
    if "differential-backups" not in keys or conf["differential-backups"] < 0:
        print("Invalid differential-backups entry in " + conf_path)
        valid = False
    if "current-differential-backups" not in keys or conf["current-differential-backups"] < 0:
        print("Invalid current-differential-backups entry in " + conf_path)
        valid = False
    if "last-full-timestamp" not in keys:
        print("Invalid last-full-timestamp entry in " + conf_path)
        valid = False
    if "last-differential-timestamp" not in keys:
        print("Invalid last-differential-timestamp entry in " + conf_path)
        valid = False
    if "use-md5" not in keys:
        print("use-md5 key missing from config")
        valid = False
    else:
        if os.path.exists(records_path):
            records: dict = toml.load(records_path)
            if conf["use-md5"]:
                if not bool(re.search("[A-z]", records[list(records.keys())[0]])):
                    print("config says to use MD5, but record file is storing mtime")
                    valid = False
            else:
                if bool(re.search("[A-z]", records[list(records.keys())[0]])):
                    print("config says to use mtime, but record file is storing MD5")
                    valid = False
    return valid

def write_toml(conf: dict, path: str):
    output = open(path, "w")
    toml.dump(conf, output)
    output.close()

def confirm(question: str, default_yes: bool=True, default_no: bool=False):
    if default_yes:
        response: str = input(question + " (Y/n)")
    elif default_no:
        response: str = input(question + " (y/N)")
    else:
        response: str = input(question + " (y/n)")
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

def item_size(path: str):
    size: float = float(os.stat(path).st_size)
    if size // 1000 < 1:
        return str(size) + "B"
    if size // 1000000 < 1:
        return str(size / 1000) + "KB"
    if size // 1000000000 < 1:
        return str(size / 1000000) + "MB"
    if size // 1000000000000 < 1:
        return str(size / 100000000) + "GB"

def is_ignored(conf: dict, item: str):
    for pattern in conf["ignored"]:
        if bool(re.match(pattern, item)):
            return True
    return False

def full_backup(conf: dict):
    working_dir: str = os.path.abspath(os.curdir)
    now: str = datetime.datetime.now().strftime("%m-%d-%Y_%a_%H:%M:%S")
    records: dict = {}
    destination_path: str = conf["destination"] + "_Full_" + now
    try:
        os.mkdir(destination_path)
    except FileExistsError:
        if confirm("The destination folder already exists at %s. Remove?" %destination_path, False, True): 
            rmtree(destination_path)
            os.mkdir(destination_path)
        else:
            exit(1)
    for path in conf["source-directories"]:
        os.mkdir(destination_path + "/" + item_from_path(path))
        backup_dir(True, path, destination_path + "/" + item_from_path(path), records, conf["use-md5"])
    os.chdir(destination_path)
    try:
        print("Finished copying files. Archiving...")
        make_archive("Full_" + now, "zip", destination_path)
    except ValueError as e:
        print("An error occured during creation of the archive. This may be okay, however.")
        print(str(e))
    print("Finished archiving. Removing working files...")
    for file in os.listdir(destination_path):
        if os.path.isdir(file):
            rmtree(destination_path + "/" + file)
    with ZipFile("Full_" + now + ".zip") as z:
        print("Full backup completed. Backed up %d items with a compressed size of %s." %(len(z.infolist()), item_size(destination_path + "/Full_" + now + ".zip")))
    print("Full backup completed")
    os.chdir(working_dir)
    write_toml(records, records_path)

def differential_backup(conf: dict):
    working_dir: str = os.path.abspath(os.curdir)
    now: str = datetime.datetime.now().strftime("%m-%d-%Y_%a_%H:%M:%S")
    records: dict = toml.load(records_path)
    destination_path: str = conf["destination"] + "_Differential_" + now
    try:
        os.mkdir(destination_path)
    except FileExistsError:
        if confirm("The destination folder already exists at %s. Remove?" %destination_path, False, True): 
            rmtree(destination_path)
            os.mkdir(destination_path)
        else:
            exit(1)
    for path in conf["source-directories"]:
        os.mkdir(destination_path + "/" + item_from_path(path))
        backup_dir(False, path, destination_path + "/" + item_from_path(path), records, conf["use-md5"])
    os.chdir(destination_path)
    try:
        print("Finished copying files. Archiving...")
        make_archive("Differential_" + now, "zip", destination_path)
    except ValueError as e:
        print("An error occured during creation of the archive. This may be okay, however.")
        print(str(e))
    print("Finished archiving. Removing working files...")
    for file in os.listdir(destination_path):
        if os.path.isdir(file):
            rmtree(destination_path + "/" + file)
    with ZipFile("Differential_" + now + ".zip") as z:
        print("Differential backup completed. Backed up %d items with a compressed size of %s." %(len(z.infolist()), item_size(destination_path + "/Differential_" + now + ".zip")))
    os.chdir(working_dir)
    
def backup_dir(full_backup: bool, path: str, destination: str, records: dict, use_md5: bool):
    previous_path: str = os.path.abspath(os.curdir)
    os.chdir(path)
    for item in os.listdir():
        if is_ignored(conf, item):
            print("Skipping " + item)
            continue
        item_path: str = os.path.abspath(path + "/" + item)
        item_destination_path: str = os.path.abspath(destination + "/" + item)
        if os.path.isdir(item_path):
            os.mkdir(item_destination_path)
            backup_dir(full_backup, item_path, item_destination_path, records, use_md5)
            if not full_backup and len(os.listdir(item_destination_path)) == 0: #delete the directory if nothing was backed up
                os.rmdir(item_destination_path)
        else:
            print("Checking file " + item_path)
            if use_md5:
                compare: str = hashlib.md5(open(item_path, "rb").read()).hexdigest()
            else:
                compare: str = str(os.path.getmtime(item_path))
            if full_backup or (item_path not in records.keys() or records[item_path] != compare):
                if full_backup:
                    records[item_path] = compare
                print(item_path + " added to backup")
                copy(item_path, item_destination_path)
    os.chdir(previous_path)

if __name__ == "__main__":
    if(not os.path.exists(conf_path)):
        gen_config_file(conf_path)
        print("config file created at %s. Please edit it before running this program again." %os.path.abspath(conf_path))
    else:
        conf: dict = toml.load(conf_path)
        if not verify_conf(conf):
            exit(1)
        if conf["last-full-timestamp"] == 0.0 or conf["current-differential-backups"] >= conf["differential-backups"]:
            backup_type: int = 0
        else:
            backup_type: int = 1
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
        if backup_type == 0:
            full_backup(conf)
            conf["current-differential-backups"] = 0
            now: datetime = datetime.datetime.now()
            conf["last-full"] = now.strftime("%m/%d/%Y %a %H:%M:%S")
            conf["last-full-timestamp"] = now.timestamp()
        else:
            if not os.path.exists(records_path):
                print("Error: record file not found. Has a full backup been run yet?")
                exit(1)
            differential_backup(conf)
            conf["current-differential-backups"] += 1
            now: datetime = datetime.datetime.now()
            conf["last-differential"] = now.strftime("%m/%d/%Y %a %H:%M:%S")
            conf["last-differential-timestamp"] = now.timestamp()
        write_toml(conf, conf_path)