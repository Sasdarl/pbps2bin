# pbps2bin
A Python 3.4+ script capable of accessing, unpacking, and rebuilding BIN files used in JoJo's Bizarre Adventure: Phantom Blood (PS2).

Optional parameters:

**-o (--outpath):** Sets a folder name or filename for the output.

**-nc (--nocompress):** Disables ZLib compression on a rebuilt BIN file or inserted file. Allows for direct access with a hex editor, in exchange for free space and disc image reinsertion.

**-m (--model):** Treat the input BIN file as a model file.

**-q (--qbextensions):** Apply the more commonly-assumed "PGM" and "DAT" extensions to exported TEX/TX2 and LXE files respectively. Only functions when there is no filelist or **--nolist** is set.

**-nl (--nolist):** Ignore the provided file list (filelist.txt) if it is available. Folders and files will instead be exported by zero-indexed number. Must be set when rebuilding a file unpacked with the flag set.

**-fo, -fi (--folder, --file):** Select a desired folder to extract, as well as a specific file to extract from that folder. When **--insert** is set, these parameters specify the file to be replaced.

**-i (--insert):** Provide a file to insert into the input BIN file. Only functions when **--folder** and **--file** are provided.
