#TODO check to make sure conf is valid
#TODO use modification time as alternative to md5
#TODO ask for confirmation for type of backup
#TODO add commandline arguments
#TODO report stats after completion
#TODO better conf generation
#TODO add eval() conditions for running types of backups
#TODO add logging

import datetime
import hashlib
import os
import re
from shutil import copy2 as copy, rmtree, make_archive
import toml

conf_path: str = "./conf.toml"
hash_path: str = "./hashes.toml"

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

def write_toml(conf: dict, path: str):
    output = open(path, "w")
    toml.dump(conf, output)
    output.close()

def item_from_path(path: str):
    if path[-1] == '/':
        return path.split("/")[-2]
    return path.split("/")[-1]

def is_ignored(conf: dict, item: str):
    for pattern in conf["ignored"]:
        if bool(re.match(pattern, item)):
            return True
    return False

def full_backup(conf: dict):
    working_dir: str = os.path.abspath(os.curdir)
    now: str = datetime.datetime.now().strftime("%m-%d-%Y_%a_%H:%M:%S")
    hash_record: dict = {}
    try:
        os.mkdir(conf["destination"] + "_Full_" + now)
    except FileExistsError:
        #TODO: ask for confirmation
        rmtree(conf["destination"] + "_Full_" + now)
        os.mkdir(conf["destination"] + "_Full_" + now)
    for path in conf["source-directories"]:
        os.mkdir(conf["destination"] + "_Full_" + now + "/" + item_from_path(path))
        backup_dir(True, path, conf["destination"] + "_Full_" + now + "/" + item_from_path(path), hash_record)
    os.chdir(conf["destination"] + "_Full_" + now)
    try:
        print("Finished copying files. Archiving...")
        make_archive("Full_" + now, "zip", conf["destination"] + "_Full_" + now)
    except ValueError as e:
        print("An error occured during creation of the archive. This may be okay, however.")
        print(str(e))
    print("Finished archiving. Removing working files...")
    for file in os.listdir(conf["destination"] + "_Full_" + now):
        if os.path.isdir(file):
            rmtree(conf["destination"] + "_Full_" + now + "/" + file)
    print("Full backup completed")
    os.chdir(working_dir)
    write_toml(hash_record, hash_path)

def differential_backup(conf: dict):
    working_dir: str = os.path.abspath(os.curdir)
    now: str = datetime.datetime.now().strftime("%m-%d-%Y_%a_%H:%M:%S")
    hash_record: dict = toml.load(hash_path)
    try:
        os.mkdir(conf["destination"] + "_Differential_" + now)
    except FileExistsError:
        #TODO: ask for confirmation
        rmtree(conf["destination"] + "_Differential_" + now)
        os.mkdir(conf["destination"] + "_Differential_" + now)
    for path in conf["source-directories"]:
        os.mkdir(conf["destination"] + "_Differential_" + now + "/" + item_from_path(path))
        backup_dir(False, path, conf["destination"] + "_Differential_" + now + "/" + item_from_path(path), hash_record)
    os.chdir(conf["destination"] + "_Differential_" + now)
    try:
        print("Finished copying files. Archiving...")
        make_archive("Differential_" + now, "zip", conf["destination"] + "_Differential_" + now)
    except ValueError as e:
        print("An error occured during creation of the archive. This may be okay, however.")
        print(str(e))
    print("Finished archiving. Removing working files...")
    for file in os.listdir(conf["destination"] + "_Differential_" + now):
        if os.path.isdir(file):
            rmtree(conf["destination"] + "_Differential_" + now + "/" + file)
    print("Differential backup completed")
    os.chdir(working_dir)
    
def backup_dir(full_backup: bool, path: str, destination: str, hash_record: dict):
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
            backup_dir(full_backup, item_path, item_destination_path, hash_record)
            if not full_backup and len(os.listdir(item_destination_path)) == 0: #delete the directory if nothing was backed up
                os.rmdir(item_destination_path)
        else:
            print("Checking file " + item_path)
            checksum: str = hashlib.md5(open(item_path, "rb").read()).hexdigest()
            if full_backup or (item_path not in hash_record.keys() or hash_record[item_path] != checksum):
                if full_backup:
                    hash_record[item_path] = checksum
                print(item_path + " added to backup")
                copy(item_path, item_destination_path)
    os.chdir(previous_path)

if __name__ == "__main__":
    if(not os.path.exists(conf_path)):
        gen_config_file(conf_path)
        print("config file created at %s. Please edit it before running this program again." %os.path.abspath(conf_path))
    else:
        conf: dict = toml.load(conf_path)
        if conf["last-full-timestamp"] == 0.0 or conf["current-differential-backups"] >= conf["differential-backups"]:
            full_backup(conf)
            conf["current-differential-backups"] = 0
            now: datetime = datetime.datetime.now()
            conf["last-full"] = now.strftime("%m/%d/%Y %a %H:%M:%S")
            conf["last-full-timestamp"] = now.timestamp()
        else:
            differential_backup(conf)
            conf["current-differential-backups"] += 1
            now: datetime = datetime.datetime.now()
            conf["last-differential"] = now.strftime("%m/%d/%Y %a %H:%M:%S")
            conf["last-differential-timestamp"] = now.timestamp()
        write_toml(conf, conf_path)