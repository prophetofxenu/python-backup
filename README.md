# python-backup
Simple differential backup program written in Python 3.
Capable of backing up multiple directories and exporting to a single ZIP. Uses UNIX mtime to check if files have been altered, but can also use MD5 for more scrutiny.

## Requirements

* Python 3
* toml
```
pip install toml
```

## Usage

To set up (after downloading):
1. Run backup.py to generate blank config file.
2. Edit conf.toml with desired settings. Comments are provided to help.
3. Run backup.py when a backup needs to be performed. The program will automatically determine whether to do a full of differential backup.

### Options

| Flag | Description | Usage |
| ---- | ----------- | ----- |
| -f, --full | Force a full backup | python backup -f |
| -d, --differential | Force a differential backup | python backup -d |
| --no-increment | Don't increae the number of differential backups run | python backup --no-increment |
| --reset-increments | Reset the number of differential backups run to zero and exit | python backup --reset-increments |
| --no-compress | Don't zip the backup upon completion | python backup --no-compress |
| -s, --stats | Print statistics and exit | python backup -s |
| -config-path | Custom path to config file | python backup -config-path path/to/conf.toml |
| -log-path | Custom path to create log file at | python backup -log-path path/to/logfile.log |
| -records-path | Custom path to read/write records file | python backup -records-path path/to/records.toml |
| -stats-path | Custom path to read/write stats file | python backup -stats-path path/to/stats.toml |