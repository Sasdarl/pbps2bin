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

def determineExtension(buf, qbFile): # QuickBMS's extensions are iconic but I'm in charge here so we use internal filenames
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
    difference = alignment-(num%alignment)
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
                dataOffset += ru32(fileOffset)
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

def get_file_name(buffer,folder,file,filelist=[],effModel=False,qbFile=False,noFolder=False): # Determine the path where the file should be stored
    outext = determineExtension(buffer,qbFile)
    if effModel:
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
        else:
            if not noFolder:
                outpath = (f"{folder}/{file}.{outext}")
            else:
                outpath = (f"{folder}_{file}.{outext}")
    return outpath

def extract_file(buf, folder, lookFolder, lookFile, model=False, useFilelist=True, qbFile=False):
    folderCount = ru32(buf,0x00) # Number of folders
    effModel = False
    if lookFolder > (folderCount - 1): # Does the folder exist?
        print(f"Invalid file {lookFolder}/{lookFile}: There are only {folderCount} folders in this file!")
        return -1
    if model and ru32(buf,0x08) != 0x20031205: # 9/0 (game/eff/eff.bin) is a unique case
        effModel = True

    lines = [] # Set up our filelist
    if useFilelist and not model:
        lines = parse_filelist("./filelist.txt")

    files = parse_header(buf,folderCount,effModel) # Set up our directory structure
    
    if lookFile > len(files[lookFolder]): # Does the file exist?
        print(f"Invalid file {lookFolder}/{lookFile}: There are only {len(files[lookFolder])} files in this folder!")
        return -1
    print(f"Accessing folder {lookFolder} ({len(files[lookFolder])} file(s))...")
    getFile = files[lookFolder][lookFile]
    fileData = get_file_data(buf,getFile[0],getFile[1],getFile[2]) # Put the file data in a buffer

    if len(fileData) > 0: # But does the file ACTUALLY exist?
        outpath = get_file_name(fileData,lookFolder,lookFile,lines,effModel,qbFile,True) # Get the best file name
        Path(f"{folder}{outpath}").parent.mkdir(parents=True,exist_ok=True) # Make the folder required
        with open(f"{folder}{outpath}", "wb") as outfile:
            for byte in fileData:
                outfile.write(struct.pack("B",byte))
        print(f"Successfully extracted to {outpath}.")
        return 0
    else:
        print(f"Invalid file {lookFolder}/{lookFile}: The file you are looking for does not exist!")
        return -1

def unpack(buf, folder, model=False, useFilelist=True, qbFile=False):
    folderCount = ru32(buf,0x00) # Number of folders
    idArray = bytearray(0) # For storing an unknown and unused value tentatively dubbed the ID
    effModel = False
    if model and ru32(buf,0x08) != 0x20031205: # 9/0 (game/eff/eff.bin) is a unique case
        effModel = True

    lines = [] # Set up our filelist
    if useFilelist and not model:
        lines = parse_filelist("./filelist.txt")

    files = parse_header(buf,folderCount,effModel) # Set up our directory structure

    getFile = []
    for i in range(folderCount):
        print(f"Folder {i}: {len(files[i])} files")
        for j in range(len(files[i])):
            getFile = files[i][j]
            fileData = get_file_data(buf,getFile[0],getFile[1],getFile[2]) # Put the file data in a buffer
            idArray.extend(wu08(getFile[3])) # Also add the ID to the corresponding array
            if len(fileData) > 0: # Does the file exist?
                curFolder = i
                if i == 12 and j == 0 and getFile[0] == 0x29D2000: # We already got the switched file
                    curFolder = 27 # But we still need the switched name
                if i == 27 and j == 0 and getFile[0] == 0x52A800:
                    curFolder = 12
                outpath = get_file_name(fileData,curFolder,j,lines,effModel,qbFile) # Get the best file name
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

def modify_header(buf, folder, file, newsize, effModel=False):
    return -1

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
                fileLength += setFile[1]
                fileLength += get_align_difference(setFile[1])
    if not effModel:
        padding = bytearray(get_align_difference(headerLength)) # Alignment
        newheader.extend(padding)
    return newheader

def append_file(input,databuffer,folder,compress=True):
    with open(input, "rb") as input_file:
        fileData = bytearray( input_file.read() )
        fileSize = len(fileData)
        if compress or folder == 8: # Game can go into an infinite loop otherwise
            fileData = zlib.compress(fileData)
            databuffer.extend(wu32(fileSize))
            databuffer.extend(fileData)
            fileSize = len(fileData)+4
        else:
            databuffer.extend(fileData)
        input_file.close()
    databuffer.extend(bytearray(get_align_difference(fileSize))) # PS2 games would take a bullet to be 0x800-aligned
    return fileSize

def insert_file(input, buf, compress=True):
    return -1

def rebuild(folder,output,model=False,compress=True,useFilelist=True):
    databuffer = bytearray(0) # This will store file data
    headerarray = []
    effModel = False
    if model and not Path(f"{folder}/filelist.id"): # 9/0 (game/eff/eff.bin) is a unique case
        effModel = True

    lines = [] # Set up our filelist
    if useFilelist and not model:
        lines = parse_filelist("./filelist.txt")

    with open(f"{Path(folder)}/filelist.id", "rb") as id_file:
        idArray = bytearray( id_file.read() ) # For the "ID" values

    if useFilelist and not model:
        filePath = Path()
        for i in range(len(lines)):
            for j in range(len(lines[i])):
                curFile = lines[i][j]
                filePath = Path(f"{folder}/{curFile[2]}/{curFile[3]}") # Get path of current file
                while len(headerarray) <= int(curFile[0]): # Add to arrays if necessary
                    headerarray.append([])
                while len(headerarray[int(curFile[0])]) <= int(curFile[1]):
                    headerarray[int(curFile[0])].append([])
                if filePath.exists():
                    fileSize = append_file(filePath,databuffer,int(curFile[0]),compress) # Append file to data buffer
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
            print(f"Folder {i} scanned: {j+1} files")
    else:
        for i in sorted(Path(folder).iterdir(),key=lambda a: numsort(a.stem)): # Sort properly by number
            if i.is_dir() and not i.is_file() and i.stem.isnumeric(): # And we only want folders with numeric names
                curFolder = int(i.stem)
                while len(headerarray) <= curFolder: # Make sure the appropriate array exists!!
                    headerarray.append([])
                for j in sorted(Path(i).iterdir(),key=lambda b: numsort(b.stem)): # Same for files
                    if j.is_file() and not j.is_dir() and j.stem.isnumeric(): # If I had to guess recursion probably isn't a thing
                        curFile = int(j.stem)
                        while len(headerarray[curFolder]) <= curFile:
                            headerarray[curFolder].append([])
                        getFile = headerarray[curFolder][curFile]
                        fileSize = append_file(j,databuffer,curFolder,compress) # Append file to data buffer
                        getFile.append(0) # See above
                        getFile.append(fileSize)
                        getFile.append(int(compress))
                        getFile.append(idArray.pop(0))
                    if not effModel: # Progress report for folders with over 500 files
                        if curFile >= 499 and (curFile+1)%100 == 0: # Just so the user knows we're not stuck
                            print(f"Please wait. {curFile+1} files complete...", end="\r", flush=True)
                if curFile >= 499:
                    print(f"Please wait. {curFile+1} files complete.  ")
                print(f"Folder {curFolder} scanned: {curFile+1} files")
    
    fileheader = rebuild_header(headerarray,effModel) # Build the header

    with open(output, "wb") as output_file:
        output_file.write(fileheader) # Write the header and data
        output_file.write(databuffer)
        output_file.close()
    return 0

parser = argparse.ArgumentParser(description='Phantom Blood PS2 BIN Extractor/Rebuilder') # QuickBMS doesn't know what these are
parser.add_argument("inpath", help="File Input (BIN/Folder)") # But I do
parser.add_argument("-o", "--outpath", help="Optional. The name used for the output folder or file.")
parser.add_argument("-nc", "--nocompress", action="store_true", help="Optional. Disables ZLib compression on files within the BIN.") # For if you want the chunkiest possible game directory
parser.add_argument("-m", "--model", action="store_true", help="Optional. Indicates a BIN file is formatted for model files.") # There are BIN files inside BIN files. It gets weirder
parser.add_argument("-qb", "--qbextensions", action="store_true", help="Optional. Gives PGM and DAT extensions in place of TEX/TX2 and LXE.") # For compatibility and nostalgia
parser.add_argument("-nl", "--nolist", action="store_true", help="Optional. Ignores the provided file list, if available.") # Ditto
parser.add_argument("-fo", "--folder", type=int, default="-1", help="Optional. Only extracts files from the desired folder.") # Ditto
parser.add_argument("-fi", "--file", type=int, default="-1", help="Optional. Only extracts the desired zero-indexed file from a folder.") # Ditto
args = parser.parse_args()

if not Path("./filelist.txt").is_file(): # If we don't have a file list, we don't have it
    args.nolist = True

if Path(args.inpath).is_file() and not Path(args.inpath).is_dir(): # BIN input is assumed   
    with open(args.inpath, "rb") as input_file:
        input_file_buffer = bytearray( input_file.read() )
        if args.outpath:
            outpath = args.outpath + "/"
        else:
            if args.model:
                outpath = (f"{Path(args.inpath).parent}/model-{Path(args.inpath).stem}/")
            else:
                if not args.folder == -1:
                    if not args.file == -1:
                        outpath = (f"{Path(args.inpath).parent}/")
                    else:
                        outpath = (f"{Path(args.inpath).parent}/{Path(args.inpath).stem}_{args.folder}/")
                else:
                    outpath = (f"{Path(args.inpath).parent}/{Path(args.inpath).stem}/")
        Path(outpath).mkdir(parents=True,exist_ok=True)
        if not args.folder == -1:
            if not args.file == -1:
                extract_file(input_file_buffer,outpath,args.folder,args.file,args.model,not args.nolist,args.qbextensions)
            else:
                if args.model and ru32(input_file_buffer,0x08) != 0x20031205:
                    file_count = 4
                else:
                    file_count = ru32(input_file_buffer,0x14+(0x10*args.folder))
                for i in range(file_count):
                    extract_file(input_file_buffer,outpath,args.folder,i,args.model,not args.nolist,args.qbextensions,True)
                print(f"Successfully extracted folder {args.folder}")
        else:
            unpack(input_file_buffer, outpath, args.model, not args.nolist, args.qbextensions)
            print(f"Unpacked BIN to {outpath}")
        input_file.close()


elif Path(args.inpath).is_dir(): # BIN output is assumed
    if args.outpath:
        outpath = args.outpath
    else:
        outpath = (f"{Path(args.inpath).stem}.bin")
    compress = not args.nocompress
    if args.model:
        args.nolist = True
        compress = False
    rebuild(args.inpath, outpath, args.model, compress, not args.nolist)
    print(f"Rebuilt BIN to {outpath}")