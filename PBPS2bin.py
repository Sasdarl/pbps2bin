import struct
import argparse
import zlib

from pathlib import Path

def ru08(buf, offset):
    return struct.unpack("<B", buf[offset:offset+1])[0] # Some of these are unused but it's nice to have them around

def ru16(buf, offset):
    return struct.unpack("<H", buf[offset:offset+2])[0]

def ru32(buf, offset):
    return struct.unpack("<I", buf[offset:offset+4])[0]

def wu08(value):
    return struct.pack("<B", value)
    
def wu16(value):
    return struct.pack("<H", value)

def wu32(value):
    return struct.pack("<I", value)

def deZLib(buf, offset, size): # Decompress a ZLib-compressed file
    localBuffer = buf[offset:offset+size]
    decompressed = zlib.decompress(localBuffer)
    return bytes(decompressed) # Array of byte integers

def determineExtension(buf, qbFile): # QuickBMS's extensions are iconic but I'm in charge here so we use internal filenames by default
    magic = buf[0:4]
    if magic[0:3].isalnum():
        magicString = magic.decode("UTF-8").rstrip("\x00")
    else:
        magicString = ""
    if magicString == "P2TX": # Commonly known as PGM
        if qbFile:
            return "pgm"
        else:
            return "tex"
    elif magicString == "TEX2": # Commonly known as nothing
        if qbFile:
            return "pgm"
        else:
            return "tx2" # I made this one up
    elif magic == bytearray([0x00, 0x10, 0x00, 0x10]): # Camera info for battle intros
        return "cam" # Cutscenes use a format called "lcm" but it's not the same one
    elif magic == bytearray([0x21, 0x01, 0xF0, 0xFF]) or buf[0:8] == bytearray([0x03, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00]): # Commonly known as DAT
        if qbFile: # The title screen files in particular have no headers
            return "dat"
        else:
            return "lxe"
    elif buf[0:8] == bytearray([0x01, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00]): # Portrait overlays
        if qbFile:
            return "dat"
        else:
            return "lxe"
    elif len(magicString) == 3:
        return magicString.lower() # But otherwise the file itself probably knows best
    elif len(magicString) == 4 and magicString[3] == "0":
        return magicString[0:3].lower()
    else:
        return "bin"

def numsort(str): # Because default numeric string sorting is the worst
    numstr = ""
    for c in str:
        if c.isnumeric():
            numstr += c
    if len(numstr) > 0:
        return int(numstr) # Let's just get an integer out of all of the numeric characters
    else:
        return -1 # And if not, lowest priority

def get_align_difference(num, alignment=0x800): # Get alignment difference for padding purposes
    difference = (alignment-(num%alignment))%alignment
    return difference
    
def parse_filelist(infile): # Convert the filelist into a two-dimensional array
    outarray = []
    with open(infile) as filelist:
        lines = filelist.readlines() # Get each text line from the file
        for line in lines:
            if line != "\n": # Make sure the line isn't empty
                linearray = [] # [Folder num, file num, name folder, name stem]
                filePos = line.split(":",1)[0] # Everything before ":" (file position)
                fileName = line.split(":",1)[1] # Everything after ":" (file name)
                fileName = fileName.strip("\n\"") # Remove quotation marks from name
                linearray += filePos.split("/") # Split position by "/" and add both elements
                linearray += fileName.rsplit("/",1) # Split name by last "/" and add both elements
                while len(outarray) <= int(linearray[0]):
                    outarray.append([])
                outarray[int(linearray[0])].insert(int(linearray[1]),linearray) # Add to the appropriate array
    return outarray

def parse_header(buf,folderCount,effModel=False): # Convert the header into a two-dimensional array
    outarray = []
    fileAdjust = False # 12/0 and 27/0 are listed at the wrong locations in the header
    if effModel:
        folderOffset = 0x04
        dataOffset = folderOffset+(folderCount*0x10)
    else:
        folderOffset = 0x10
    for i in range(folderCount):
        outarray.append([]) # Set up inner array
        if effModel:
            fileOffset = folderOffset
            fileCount = 4
        else:
            fileOffset = ru32(buf,folderOffset) # This only needs to exist in files with variable folders
            fileCount = ru32(buf,folderOffset+4)
        for j in range(fileCount):
            filearray = [] # [File offset, file size, compressed, ID]
            if effModel:
                filearray.append(dataOffset)
                filearray.append(ru32(buf,fileOffset))
                filearray.append(0) # There's no flag for this
                filearray.append(0) # This isn't in the format
                dataOffset += ru32(buf,fileOffset)
                fileOffset += 0x04
            else:
                dataOffset = ru32(buf,fileOffset)
                if i == 12 and j == 0 and dataOffset == 0x29D2000:
                    fileOffset = 0x10+(0x10*27) # The aforementioned header fix
                    fileAdjust = True
                elif i == 27 and j == 0 and dataOffset == 0x52A800:
                    fileOffset = 0x10+(0x10*12) # We check the offset because in any other case than vanilla we'll have already fixed it
                    fileAdjust = True
                compressed = (ru16(buf,fileOffset+8)&0x2000) # Check compression
                compressed >>= 13
                filearray.append(dataOffset)
                filearray.append(ru32(buf,fileOffset+4))
                filearray.append(compressed)
                filearray.append(ru08(buf,fileOffset+10))
                if fileAdjust:
                    fileOffset = 0x10+(0x10*i)
                fileOffset += 0x10
            outarray[i].append(filearray)
        folderOffset += 0x10
    return outarray

def get_file_data(buf,offset,size,compressed=0): # Get (and decompress if necessary) a file as a bytearray
    if compressed == 1:
        size += get_align_difference(size) # The English patch messed up the sizes
        tempBuf = buf[offset+4:offset+size] # It's easier to just bake the fix in
        fileData = deZLib(tempBuf,0,len(tempBuf)) # Decompress if needed
        if not len(fileData) == ru32(buf,offset):
            print(f"Incorrect file size specified! Attempting to ignore...")
    else:
        if size > 0:
            fileData = buf[offset:offset+size]
        else:
            fileData = []
    return fileData

def get_file_name(buffer,folder,file,filelist=[],model=False,qbFile=False,noFolder=False): # Determine the path where the file should be stored
    outext = determineExtension(buffer,qbFile)
    if model:
        if file == 0: # Might as well name them
            outpath = (f"model.{outext}")
        elif file == 1:
            outpath = (f"texture.{outext}")
        elif file == 2: # If someone figures out what these are, let me know
            outpath = (f"unknown.{outext}")
        else:
            outpath = (f"unknown{file-1}.{outext}")
        if not noFolder:
            outpath = (f"{folder}/{outpath}")
    else:
        if len(filelist) > 0:
            outpath = (f"{filelist[folder][file][3]}")
            if not noFolder:
                outpath = (f"{filelist[folder][file][2]}/{outpath}")
        elif not noFolder:
            outpath = (f"{folder}/{file}.{outext}")
        else:
            outpath = (f"{folder}_{file}.{outext}")
    return outpath

def append_file(input,databuffer,folder,compress=True,effModel=False): # Add file to the end of the buffer
    with open(input, "rb") as input_file:
        fileData = bytearray( input_file.read() )
        fileSize = len(fileData)
        if not effModel and (compress or folder == 8): # Game can go into an infinite loop otherwise
            fileData = zlib.compress(fileData)
            databuffer.extend(wu32(fileSize))
            databuffer.extend(fileData)
            fileSize = len(fileData)+4
        else:
            databuffer.extend(fileData)
        input_file.close()
    if not effModel:
        databuffer.extend(bytearray(get_align_difference(fileSize))) # PS2 games would take a bullet to be 0x800-aligned
    return fileSize

def modify_header(buf, folder, file, newsize, compress=True, effModel=False): # Adjust header to change one file's size
    if effModel:
        fileOffset = 0x04+(folder*0x10)+(file*0x04) # List of sizes
        buf[fileOffset:fileOffset+4] = wu32(newsize) # Just find the one we need and change it
    else:
        folderCount = ru32(buf,0)
        difference = 0 # This will keep track of how much we need to adjust things by
        for i in range(folderCount-folder): # Skip to the folder we need. We'll make up for it as we go
            fileOffset = ru32(buf, 0x10+(i+folder)*0x10)
            fileCount = ru32(buf, 0x14+(i+folder)*0x10)
            for j in range(fileCount):
                curFile = fileOffset+(0x10*j) # Find the offset for the file
                if i == 0 and j <= file: # Don't do anything until we get to the replacement file
                    if j == file: # We're at the replacement file
                        curFileSize = ru32(buf,curFile+4)+get_align_difference(ru32(buf,curFile+4))
                        difference += newsize+get_align_difference(newsize) # Calculate difference
                        difference -= curFileSize
                        buf[curFile+4:curFile+8] = wu32(newsize)
                        if compress or folder == 8: # Set compression flag
                            buf[curFile+8:curFile+10] = wu16(0x2000)
                        else:
                            buf[curFile+8:curFile+10] = wu16(0)
                else: # This runs for all files after the replacement
                    curFileOffset = ru32(buf,curFile)
                    buf[curFile:curFile+4] = wu32(curFileOffset+difference) # Add the difference
    return 0

def rebuild_header(headerarray, effModel=False): # Reconstruct a BIN file header from a two-dimensional array
    newheader = bytearray(0)
    newheader.extend(wu32(len(headerarray))) # Both types start with the number of folders

    if not effModel:
        folderheader = bytearray(0) # We have to iterate over the folders to calculate the header length
        foldersLength = 0x10+(len(headerarray)*0x10) # And we need the header length to iterate over the files
        headerLength = foldersLength # It's very much a catch-22
        for folder in headerarray:
            folderheader.extend(wu32(headerLength)) # Folder header line
            folderheader.extend(wu32(len(folder)))
            folderheader.extend(wu32(0))
            folderheader.extend(wu32(0))
            headerLength += 0x10*len(folder) # Allocate space for the files in the folder
        newheader.extend(wu32(headerLength))
        newheader.extend(wu32(0x20031205)) # Unused value. Possibly a build date for the original software?
        newheader.extend(wu32(0))
        newheader.extend(folderheader) # Add our folder header to the overall header
        fileLength = headerLength+get_align_difference(headerLength) # Used to calculate file offsets
    
    for i in range(len(headerarray)):
        for j in range(len(headerarray[i])):
            setFile = headerarray[i][j]
            if not effModel:
                newheader.extend(wu32(fileLength)) # Data offset
            newheader.extend(wu32(setFile[1])) # The special case eff.bin only uses file sizes
            if not effModel:
                newheader.extend(wu16(setFile[2]*0x2000)) # Compression
                newheader.extend(wu16(setFile[3])) # Special "ID"
                newheader.extend(wu32(0))
                fileLength += setFile[1] # Increment by file size including padding
                fileLength += get_align_difference(setFile[1])
        while effModel and j < 3:
            newheader.extend(wu32(0)) # eff.bin demands four files a folder
            j += 1

    if not effModel:
        padding = bytearray(get_align_difference(headerLength)) # Alignment
        newheader.extend(padding)
    return newheader

def extract_file(buf, folder, lookFolder, lookFile, model=False, useFilelist=True, qbFile=False, fileName=""):
    folderCount = ru32(buf,0x00) # Number of folders
    effModel = False
    if lookFolder > (folderCount - 1): # Does the folder exist?
        print(f"Invalid file {lookFolder}/{lookFile}: There are only {folderCount} folders in this file!")
        return -1
    if model and ru32(buf,0x08) != 0x20031205: # 9/0 (game/eff/eff.bin) is a unique case
        effModel = True
        compress = False

    lines = [] # Set up our filelist
    if useFilelist:
        lines = parse_filelist("./filelist.txt")

    files = parse_header(buf,folderCount,effModel) # Set up our directory structure
    
    if lookFile > len(files[lookFolder]): # Does the file exist?
        print(f"Invalid file {lookFolder}/{lookFile}: There are only {len(files[lookFolder])} file(s) in this folder!")
        return -1
    getFile = files[lookFolder][lookFile]
    fileData = get_file_data(buf,getFile[0],getFile[1],getFile[2]) # Put the file data in a buffer

    if len(fileData) > 0: # But does the file ACTUALLY exist?
        if len(fileName) > 0:
            outpath = (f"{folder}{fileName}") # It's important that we allow ourselves to be passed a name for one file
        else: # Otherwise, get the best file name
            outpath = get_file_name(fileData,lookFolder,lookFile,lines,model,qbFile,True)
            outpath = (f"{folder}{outpath}")
        Path(outpath).parent.mkdir(parents=True,exist_ok=True)
        with open(outpath, "wb") as outfile:
            for byte in fileData:
                outfile.write(struct.pack("B",byte))
        return 0
    else:
        print(f"Invalid file {lookFolder}/{lookFile}: The file you are looking for does not exist!")
        return -1

def insert_file(buf, input, output, repFolder, repFile, model=False, compress=True):
    effModel = False
    if model and ru32(buf,0x08) != 0x20031205: # 9/0 (game/eff/eff.bin) is a unique case
        effModel = True
        compress = False

    if effModel:
        folderCount = ru32(buf,0)
        fileOffset = 0x04
        dataOffset = fileOffset+(0x10*folderCount)
        for i in range(repFolder*4+repFile-1): # Once again: it is a series of file sizes
            dataOffset += ru32(fileOffset)
            fileOffset += 0x04
        fileSize = ru32(buf, fileOffset)
        afterBuffer = buf[dataOffset+fileSize::] # Buffer for everything after the original file
    else:
        fileOffset = ru32(buf, 0x10+(repFolder*0x10)) # We just need the offset and size of the file we're replacing
        fileOffset += repFile*0x10
        dataOffset = ru32(buf, fileOffset)
        fileSize = ru32(buf, fileOffset+4)
        fileSizeRounded = fileSize + get_align_difference(fileSize)
        afterBuffer = buf[dataOffset+fileSizeRounded::] # Buffer for everything after the original file

    newBuffer = buf[0:dataOffset] # Buffer for everything before the original file
    fileSize = append_file(Path(input),newBuffer,repFolder,compress,effModel) # Append the new file to the first buffer
    newBuffer.extend(afterBuffer) # And stick the second buffer back on afterward

    modify_header(newBuffer,repFolder,repFile,fileSize,compress,effModel) # Finally, adjust the header
    with open(output, "wb") as output_file:
        for byte in newBuffer:
            output_file.write(struct.pack("B",byte))
    return 0

def unpack(buf, folder, model=False, useFilelist=True, qbFile=False):
    folderCount = ru32(buf,0x00) # Number of folders
    idArray = bytearray(0) # For storing an unknown and unused value tentatively dubbed the ID
    effModel = False
    if model and ru32(buf,0x08) != 0x20031205: # 9/0 (game/eff/eff.bin) is a unique case
        effModel = True
        compress = False

    lines = [] # Set up our filelist
    if useFilelist:
        lines = parse_filelist("./filelist.txt")

    files = parse_header(buf,folderCount,effModel) # Set up our directory structure

    getFile = []
    for i in range(folderCount):
        print(f"Folder {i}: {len(files[i])} file(s)")
        for j in range(len(files[i])):
            getFile = files[i][j]
            fileData = get_file_data(buf,getFile[0],getFile[1],getFile[2]) # Put the file data in a buffer
            idArray.extend(wu08(getFile[3])) # Also add the ID to the corresponding array
            if len(fileData) > 0: # Does the file exist?
                curFolder = i
                if i == 12 and j == 0 and getFile[0] == 0x29D2000: # We already got the switched file
                    curFolder = 27 # But we still need the switched name
                elif i == 27 and j == 0 and getFile[0] == 0x52A800:
                    curFolder = 12
                outpath = get_file_name(fileData,curFolder,j,lines,model,qbFile) # Get the best file name
                Path(f"{folder}{outpath}").parent.mkdir(parents=True,exist_ok=True) # Make the folder required
                with open(f"{folder}{outpath}", "wb") as outfile:
                    for byte in fileData:
                        outfile.write(struct.pack("B",byte))
            if not effModel: # Progress report for folders with over 500 files
                if j >= 499 and (j+1)%100 == 0: # Just so the user knows we're not stuck
                    print(f"Please wait. {j+1} files complete...", end="\r", flush=True)
                if j > 499 and j == len(files[i]) - 1:
                    print(f"Please wait. {j+1} files complete.  ")

    if not effModel:
        outid = (f"{folder}filelist.id")
        with open(outid, "wb") as id_file: # Write the ID array
            id_file.write(idArray)
            id_file.close()
    return 0

def rebuild(folder,output,model=False,compress=True,useFilelist=True):
    databuffer = bytearray(0) # This will store file data
    headerarray = []
    effModel = False
    if model and not Path(f"{folder}/filelist.id").exists(): # 9/0 (game/eff/eff.bin) is a unique case
        effModel = True
        compress = False

    lines = [] # Set up our filelist
    if useFilelist:
        lines = parse_filelist("./filelist.txt")

    idArray = []
    if not effModel and Path(f"{folder}/filelist.id").exists():
        with open(f"{Path(folder)}/filelist.id", "rb") as id_file:
            idArray = bytearray( id_file.read() ) # For the "ID" values

    if useFilelist:
        filePath = Path()
        for i in range(len(lines)):
            j = -1
            for j in range(len(lines[i])):
                curFile = lines[i][j]
                filePath = Path(f"{folder}/{curFile[2]}/{curFile[3]}") # Get path of current file
                while len(headerarray) <= int(curFile[0]): # Add to arrays if necessary
                    headerarray.append([])
                while len(headerarray[int(curFile[0])]) <= int(curFile[1]):
                    headerarray[int(curFile[0])].append([])
                if filePath.exists():
                    fileSize = append_file(filePath,databuffer,int(curFile[0]),compress,effModel) # Append file to data buffer
                    getFile = headerarray[int(curFile[0])][int(curFile[1])]
                    getFile.append(0) # We don't use file offsets in the header reassembly method
                    getFile.append(fileSize)
                    getFile.append(int(compress))
                    getFile.append(idArray.pop(0)) # We are assuming the filelist is sorted. "Be careful," I would say if this mattered
                else:
                    print(f"File {filePath} does not exist! Skipping...")
                if not effModel: # Progress report for folders with over 500 files
                    if j >= 499 and (j+1)%100 == 0: # Just so the user knows we're not stuck
                        print(f"Please wait. {j+1} files complete...", end="\r", flush=True)
                    if j > 499 and j == len(lines[i]) - 1:
                        print(f"Please wait. {j+1} files complete.  ")
            print(f"Folder {i} scanned: {j+1} file(s)")
    else:
        for i in sorted(Path(folder).iterdir(),key=lambda a: numsort(a.stem)): # Sort properly by number
            curFile = -1
            if i.is_dir() and not i.is_file() and i.stem.isnumeric(): # And we only want folders with numeric names
                curFolder = int(i.stem)
                while len(headerarray) <= curFolder: # Make sure the appropriate array exists!!
                    headerarray.append([])
                for j in sorted(Path(i).iterdir(),key=lambda b: numsort(b.stem)): # Same for files
                    if j.is_file() and not j.is_dir(): # If I had to guess recursion probably isn't a thing
                        if j.stem.isnumeric(): # Model files are labeled
                            curFile = int(j.stem)
                        else:
                            curFile = curFile+1
                        while len(headerarray[curFolder]) <= curFile:
                            headerarray[curFolder].append([])
                        getFile = headerarray[curFolder][curFile]
                        fileSize = append_file(j,databuffer,curFolder,compress,effModel) # Append file to data buffer
                        getFile.append(0) # See above
                        getFile.append(fileSize)
                        getFile.append(int(compress))
                        if len(idArray) > 0: # effModel doesn't know about this
                            getFile.append(idArray.pop(0))
                        else:
                            getFile.append(0)
                    if not effModel: # Progress report for folders with over 500 files
                        if curFile >= 499 and (curFile+1)%100 == 0: # Just so the user knows we're not stuck
                            print(f"Please wait. {curFile+1} files complete...", end="\r", flush=True)
                if curFile >= 499:
                    print(f"Please wait. {curFile+1} files complete.  ")
                print(f"Folder {curFolder} scanned: {curFile+1} file(s)")
    
    fileheader = rebuild_header(headerarray,effModel) # Build the header

    with open(output, "wb") as output_file:
        output_file.write(fileheader) # Write the header and data
        output_file.write(databuffer)
        output_file.close()
    return 0

parser = argparse.ArgumentParser(description='Phantom Blood PS2 BIN Extractor/Rebuilder') # QuickBMS doesn't know what these are
parser.add_argument("inpath", help="File Input (BIN/Folder)") # But I do
parser.add_argument("-o", "--outpath", type=str, default="", help="Optional. The name used for the output folder or file.")
parser.add_argument("-nc", "--nocompress", action="store_true", help="Optional. BIN output only. Disables ZLib compression on files within the BIN.") # For if you want the chunkiest possible game directory
parser.add_argument("-m", "--model", action="store_true", help="Optional. Indicates a BIN file or folder is formatted as a model file.") # There are BIN files inside BIN files. It gets weirder
parser.add_argument("-qb", "--qbextensions", action="store_true", help="Optional. BIN input only. Gives PGM and DAT extensions in place of TEX/TX2 and LXE.") # For compatibility and nostalgia
parser.add_argument("-nl", "--nolist", action="store_true", help="Optional. Ignores the provided file list, if available.") # Ditto
parser.add_argument("-fo", "--folder", type=int, default="-1", help="Optional. Extracts files from the desired folder, or specifies insertion folder.") # Ditto
parser.add_argument("-fi", "--file", type=int, default="-1", help="Optional. Extracts the desired file from a folder, or specifies insertion file.") # Ditto
parser.add_argument("-i", "--insert", type=str, default="", help="Optional. Indicates the file to insert at the provided folder and file number.") # Ditto

args = parser.parse_args()

compress = not args.nocompress # For convenience
filelist = not args.nolist
if args.model or not Path("./filelist.txt").is_file(): # If we don't have a file list, we don't have it
    filelist = False # And if we're handling the file as a model we can't use the list anyway
if args.folder == -1: # Let's not look for a file without a folder to look in
    args.file = -1
if args.file == -1 or not (Path(args.insert).is_file() and not Path(args.insert).is_dir()):
    args.insert = False # And we can't insert anything if we don't know where to look

if Path(args.inpath).is_file() and not Path(args.inpath).is_dir(): # BIN input is assumed
    with open(args.inpath, "rb") as input_file:
        input_buffer = bytearray( input_file.read() )

        outpath = "./"
        if len(args.outpath) > 0: # Outpath takes priority!!
            outpath += args.outpath
        elif args.insert: # After that is insertion, since that is based on an existing file
            outpath = (f"{Path(args.inpath).parent}/{Path(args.inpath).stem}_modified{Path(args.inpath).suffix}")
        elif not args.folder == -1: # Then check for individual folder/file...
            if args.file == -1: # We can get away with just sending an individual file to the input directory
                if args.model: # If we have a model file, we should specify it.
                    outpath = (f"{Path(outpath).parent}/model-{Path(args.inpath).stem}_{args.folder}")
                else:
                    outpath = (f"{Path(outpath).parent}/{Path(args.inpath).stem}_{args.folder}")
        else:
            outpath = (f"{Path(args.inpath).parent}/{Path(args.inpath).stem}") # Finally, the default case.

        if not args.insert and not (len(args.outpath) > 0 and not args.file == -1):
            if not outpath == "./": # .// would look strange in the output
                outpath += "/"

        output_folder = outpath.rsplit("/",1)[0]+"/" # Split output into folder and filename
        output_file = outpath.rsplit("/",1)[1]

        if args.insert: # Insertion needs the most parts to work. Let's handle that first
            Path(output_folder).mkdir(parents=True,exist_ok=True) # Make the necessary folder
            ins = insert_file(input_buffer,args.insert,outpath,args.folder,args.file,args.model,compress)
            if ins == 0: # That's right, we're using status codes now. Deal with it
                print(f"Successfully inserted {args.insert} into {outpath}")
        else:
            if not args.model and not (len(args.outpath) > 0 and not args.file == -1): # Do NOT make "model-/"!
                Path(output_folder).mkdir(parents=True,exist_ok=True)
            if not args.folder == -1: # Folder/file extraction is next...
                if not args.file == -1: # Individual file
                    ex = extract_file(input_buffer,output_folder,args.folder,args.file,args.model,filelist,args.qbextensions,output_file)
                    if ex == 0:
                        print(f"Successfully extracted file {args.folder}/{args.file} to {outpath}")
                else: # Folder extraction
                    if args.model and ru32(input_buffer,0x08) != 0x20031205: # We know how many files are in an effModel folder
                        file_count = 4
                        for i in range(file_count): # Or at least we know the maximum.
                            if ru32(input_buffer,0x04+i*0x04) == 0: # So if we find a file with size 0, we have our file count
                                file_count = i
                    else:
                        file_count = ru32(input_buffer,0x14+(0x10*args.folder)) # For regular files, we have to look
                    for i in range(file_count): # Folder extraction. Iterate over files in the folder
                        ex = extract_file(input_buffer,output_folder,args.folder,i,args.model,filelist,args.qbextensions,output_file)
                    if ex == 0:
                        print(f"Successfully extracted folder {args.folder} to {outpath}")
            else: # Otherwise, it's time for the standard unpack
                un = unpack(input_buffer, output_folder, args.model, filelist, args.qbextensions)
                if un == 0:
                    print(f"Successfully unpacked BIN to {output_folder}")
        input_file.close()

elif Path(args.inpath).is_dir(): # BIN output is assumed
    if args.outpath: # Outpath takes priority, again
        outpath = args.outpath
    else: # Otherwise, nothing better to do than the default
        outpath = (f"{Path(args.inpath).stem}.bin")

    re = rebuild(args.inpath, outpath, args.model, compress, filelist) # Rebuild time.
    if re == 0:
        print(f"Successfully rebuilt BIN to {outpath}")