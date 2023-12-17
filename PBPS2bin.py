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

def deZLib(buf,offset,size): # Decompress a ZLib-compressed file
    localBuffer = buf[offset:offset+size]
    decompressed = zlib.decompress(localBuffer)
    return bytes(decompressed) # Array of byte integers

def determineExtension(buf): # QuickBMS's extensions are iconic but I'm in charge here so we use internal filenames
    magic = buf[0:4]
    if magic[0:3].isalnum():
        magicString = magic.decode("UTF-8").rstrip("\x00")
    else:
        magicString = ""
    if magicString == "P2TX": # Commonly known as PGM
        if args.qbextensions:
            return "pgm"
        else:
            return "tex"
    elif magicString == "TEX2": # Commonly known as nothing
        if args.qbextensions:
            return "pgm"
        else:
            return "tx2" # I made this one up
    elif magic == bytearray([0x00, 0x10, 0x00, 0x10]): # Camera info for battle intros
        return "cam"
    elif magic == bytearray([0x21, 0x01, 0xF0, 0xFF]): # Commonly known as DAT
        if args.qbextensions:
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
    for d in range(20-len(numstr)): # We're basically just standardizing the lengths
        numstr = "0" + numstr # God help those who decide to put 18 zeroes in front of a filename
    return numstr

def unpack(buf, folder, model):
    folderCount = ru32(buf,0x00) # Number of folders
    if model:
        folderOffset = 0x04
        dataOffset = folderCount*0x10+0x04
    else:
        idArray = bytearray(0)
        folderOffset = 0x10
        fileOffset = folderCount*0x10+0x10
    for i in range(folderCount):
        if model:
            fileCount = 4
        else:
            dataOffset = ru32(buf,folderOffset)
            fileCount = ru32(buf,folderOffset+4)
            print(f"Folder {i}: {fileCount} files")
        outfolder = (f"{folder}{i}/")
        Path(outfolder).mkdir(parents=True,exist_ok=True) # Make numeric directories
        for j in range(fileCount):
            if model:
                fileOffset = folderOffset+j*0x04
                dataSize = ru32(buf,fileOffset)
                if dataSize > 0:
                    fileData = buf[dataOffset:dataOffset+dataSize]
                else:
                    fileData = []
                dataOffset += dataSize
            else:
                dataOffset = ru32(buf,fileOffset)
                dataSize = ru32(buf,fileOffset+4)
                compressed = (ru16(buf,fileOffset+8)&0x2000) # Check compression
                compressed >>= 13
                idArray.extend(wu08(buf[fileOffset+10]))
                if compressed == 1:
                    paddedSize = dataSize + 0x800-(dataSize%0x800) # The English patch messed up the sizes
                    tempBuf = buf[dataOffset+4:dataOffset+paddedSize] # It's easier to just bake the fix in
                    fileData = deZLib(tempBuf,0,len(tempBuf)) # Decompress if needed
                else:
                    fileData = buf[dataOffset:dataOffset+dataSize]
            if len(fileData) > 0:
                outext = determineExtension(fileData)
                if model:
                    if j == 0: # Might as well name them
                        outpath = (f"{outfolder}model.{outext}")
                    elif j == 1:
                        outpath = (f"{outfolder}texture.{outext}")
                    elif j == 2: # If someone figures out what these are, let me know
                        outpath = (f"{outfolder}unknown.{outext}")
                    else:
                        outpath = (f"{outfolder}unknown2.{outext}")
                else:
                    outpath = (f"{outfolder}{j}.{outext}")
                    if i == 12 and j == 0 and dataOffset == 0x29D2000: # I wish I knew why too
                        outpath = (f"{folder}27/{j}.{outext}")
                        Path(f"{folder}27/").mkdir(parents=True,exist_ok=True)
                    if i == 27 and j == 0 and dataOffset == 0x52A800:
                        outpath = (f"{folder}12/{j}.{outext}")
                with open(outpath, "wb") as outfile:
                    for byte in fileData:
                        outfile.write(struct.pack("B",byte))
                if not model: # Just so the user knows we're not stuck
                    fileOffset += 0x10
                    if j >= 499 and (j+1)%100 == 0:
                        print(f"Please wait. {j+1} files complete...", end="\r", flush=True)
                    if j > 499 and j == fileCount - 1:
                        print(f"Please wait. {j+1} files complete.  ")
        folderOffset += 0x10
    if not model:
        outid = (f"{folder}filelist.id")
        with open(outid, "wb") as id_file: # These aren't necessary but until I figure out how they're calculated
            id_file.write(idArray) # this will have to do
            id_file.close()
    return 0

def rebuild(folder,output,compress):
        folders = 0
        totalfiles = 0
        databuffer = bytearray(0)
        folderheader = bytearray(0)
        fileheader = bytearray(0)
        with open(f"{Path(folder)}//filelist.id", "rb") as id_file:
            idArray = bytearray( id_file.read() )
        for i in sorted(Path(folder).iterdir(),key=lambda a: numsort(a.stem)): # Sort properly by number
            if i.is_dir() and not i.is_file() and i.stem.isnumeric(): # And we only want folders with numeric names
                folders += 1
                files = 0
                fileheaderoff = len(fileheader)
                for j in sorted(Path(i).iterdir(),key=lambda b: numsort(b.stem)): # Same for files
                    if j.is_file() and not j.is_dir() and j.stem.isnumeric(): # If I had to guess recursion probably isn't a thing
                        files += 1
                        fileheader.extend(wu32(len(databuffer)))
                        with open(j, "rb") as input_file:
                            fileData = bytearray( input_file.read() )
                            originalSize = len(fileData)
                            if compress or folders == 8: # Game can go into an infinite loop otherwise
                                zLibData = zlib.compress(fileData)
                                zLibSize = len(zLibData)
                                databuffer.extend(wu32(originalSize))
                                databuffer.extend(zLibData)
                                fileheader.extend(wu32(zLibSize+4)) # Add four for the original size at the front
                                fileheader.extend(wu16(0x2000))
                            else:
                                databuffer.extend(fileData)
                                fileheader.extend(wu32(originalSize))
                                fileheader.extend(wu16(0))
                            fileheader.extend(wu16(idArray[totalfiles+files-1])) # Put whatever this is there
                            fileheader.extend(wu32(0))
                            input_file.close()
                        remainder = len(databuffer)%0x800 # PS2 games would take a bullet to be 0x800-aligned
                        if remainder != 0:
                            databuffer.extend(bytes(0x800-remainder))
                folderheader.extend(wu32(fileheaderoff))
                folderheader.extend(wu32(files))
                folderheader.extend(bytes(8))
                totalfiles += files
                print(f"Folder {i} scanned: {files} files")
        folderheadersize = len(folderheader)+0x10
        headersize = len(fileheader)+folderheadersize
        remainder = headersize%0x800
        if remainder != 0:
            fileheader.extend(bytes(0x800-remainder))
            headersize = len(fileheader)+folderheadersize
        for k in range(folders): # Update folder offsets to account for the headers
            cursize = ru32(folderheader,k*0x10)
            folderheader[k*0x10:k*0x10+4] = wu32(cursize+folderheadersize)
        for l in range(totalfiles): # Ditto for the file offsets
            cursize = ru32(fileheader,l*0x10)
            fileheader[l*0x10:l*0x10+4] = wu32(cursize+headersize)
        with open(output, "wb") as output_file:
            topheader = bytearray(0) # Bytearrays are simply easier to write
            topheader.extend(wu32(folders))
            topheader.extend(wu32(headersize-0x800+remainder))
            topheader.extend(wu32(0x20031205)) # The game doesn't read this. It might be the format's creation month?
            topheader.extend(wu32(0))
            output_file.write(topheader)
            output_file.write(folderheader)
            output_file.write(fileheader)
            output_file.write(databuffer)
            output_file.close()

def rebuild_model(folder,output):
        folders = 0
        totalfiles = 0
        databuffer = bytearray(0)
        fileheader = bytearray(0)
        for i in sorted(Path(folder).iterdir(),key=lambda a: numsort(a.stem)):
            if i.is_dir() and not i.is_file() and i.stem.isnumeric(): # Numeric folders only
                folders += 1
                file = 0
                fileheaderoff = len(fileheader)
                for j in sorted(Path(i).iterdir(),key=lambda b: numsort(b.stem)):
                    if j.is_file() and not j.is_dir(): # But named files are fine
                        with open(j, "rb") as input_file:
                            fileData = bytearray( input_file.read() )
                            if j.name == "texture.tx2" and file == 0: # Add any necessary zero entries
                                    fileheader.extend(wu32(0))
                                    file += 1
                            if j.name == "unknown.bin":
                                for k in range(2-file):
                                    fileheader.extend(wu32(0))
                                    file += 1
                            if j.name == "unknown2.bin":
                                for k in range(3-file):
                                    fileheader.extend(wu32(0))
                                    file += 1
                            fileheader.extend(wu32(len(fileData)))
                            databuffer.extend(fileData)
                            file += 1
                if file < 4:
                    for k in range(4-file): # Do so at the end, too
                        fileheader.extend(wu32(0))
        with open(output, "wb") as output_file:
            output_file.write(wu32(folders))
            output_file.write(fileheader)
            output_file.write(databuffer)
            output_file.close()

parser = argparse.ArgumentParser(description='Phantom Blood PS2 BIN Extractor/Rebuilder') # QuickBMS doesn't know what these are
parser.add_argument("inpath", help="File Input (BIN)") # But I do
parser.add_argument("-o", "--outpath", help="Optional. The name used for the output folder or file.")
parser.add_argument("-nc", "--nocompress", action="store_true", help="Optional. Disables ZLib compression on files within the BIN.") # For if you want the chunkiest possible game directory
parser.add_argument("-m", "--model", action="store_true", help="Optional. Indicates a BIN file is formatted for model files.") # There are BIN files inside BIN files. It gets weirder
parser.add_argument("-q", "--qbextensions", action="store_true", help="Optional. Gives PGM and DAT extensions in place of TEX/TX2 and LXE.") # For compatibility and nostalgia
args = parser.parse_args()
if Path(args.inpath).is_file() and not Path(args.inpath).is_dir(): # BIN input is assumed   
    with open(args.inpath, "rb") as input_file:
        input_file_buffer = bytearray( input_file.read() )
        if args.outpath:
            outpath = args.outpath + "/"
        else:
            if args.model:
                outpath = (f"{Path(args.inpath).parent}/model-{Path(args.inpath).stem}/")
            else:
                outpath = (f"{Path(args.inpath).parent}/{Path(args.inpath).stem}/")
        Path(outpath).mkdir(parents=True,exist_ok=True)
        unpack(input_file_buffer,outpath,args.model)
        input_file.close()
        print(f"Unpacked BIN to {outpath}")


elif Path(args.inpath).is_dir(): # BIN output is assumed
    if args.outpath:
        outpath = args.outpath
    else:
        outpath = (f"{Path(args.inpath).stem}.bin")
    if args.model:
        rebuild_model(args.inpath,outpath)
    else:
        compress = not args.nocompress
        rebuild(args.inpath,outpath,compress)
    print(f"Rebuilt BIN to {outpath}")