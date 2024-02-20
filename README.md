# pbps2bin
A Python 3.4+ script capable of unpacking and repacking BIN files used in JoJo's Bizarre Adventure: Phantom Blood (PS2).

Optional parameters:

**-o (--outpath):** Set a folder name or filename for the output.

**-nc (--nocompress):** Disable ZLib compression on the rebuilt BIN file. Allows for direct access with a hex editor, in exchange for free space and disc image reinsertion.

**-m (--model):** Treat the BIN file to be unpacked or rebuilt as a model file.

**-q (--qbextensions):** Apply the more commonly-assumed "PGM" and "DAT" extensions to TEX and LXE files respectively. Only functions when there is no filelist or **--nolist** is set.

**-nl (--nolist):** Ignore the provided file list (filelist.txt) if it is available. Folders and files will instead be exported by zero-indexed number.
