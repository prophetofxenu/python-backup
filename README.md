# python-backup
Simple differential backup program written in Python 3

Requires toml
```
pip install toml
```

Capable of backing up multiple directories and exporting to a single ZIP. Uses MD5 to check for altered files. (I'm aware that this is inefficient, working on using UNIX file modification timestamps instead.)

To set up (after downloading):
1. Run backup.py to generate blank config file.
2. Edit conf.toml with desired settings. Comments are provided to help.
3. Run backup.py when a backup needs to be performed. The program will automatically determine whether to do a full of differential backup.
