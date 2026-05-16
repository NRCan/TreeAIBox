#
# lascanopyPro.py
#
# (c) 2025 rapidlasso GmbH - http://rapidlasso.com
#     fast tools to catch reality
#
# uses lascanopy.exe to generate forestry metrics
#
# LiDAR input:   LAS/LAZ/BIN/TXT/SHP/BIL/ASC/DTM
# raster output: BIL/ASC/IMG/TIF/DTM/PNG/JPG
#
# for licensing see http://lastools.org/LICENSE.txt
#

import sys, os, arcgisscripting, subprocess


def check_output(command, console):
    if console == True:
        process = subprocess.Popen(command)
    else:
        process = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True
        )
    output, error = process.communicate()
    returncode = process.poll()
    return returncode, output


### create the geoprocessor object
gp = arcgisscripting.create(9.3)

### get number of arguments
argc = len(sys.argv)

is64 = sys.argv[argc - 2] != "true"
exename = "lascanopy"

### optional use old 32 bit version
if is64:
    exename += "64"

### report that something is happening
gp.AddMessage("Starting " + exename + " ...")

### report arguments (for debug)
# gp.AddMessage("Arguments:")
# for i in range(0, argc):
#    gp.AddMessage("[" + str(i) + "]" + sys.argv[i])

### go back to lastools from \LAStools\ArcGIS_toolbox\scripts
lastools_bin = os.path.dirname(os.path.dirname(os.path.dirname(sys.argv[0])))

### make sure the path does not contain spaces
if lastools_bin.count(" ") > 0:
    gp.AddMessage("Error. Path to .\\lastools installation contains spaces.")
    gp.AddMessage("This does not work: " + lastools_bin)
    gp.AddMessage("This would work:    C:\\software\\lastools")
    sys.exit(1)

### complete the path to where the LAStools executables are
lastools_bin = lastools_bin + "\\bin"

### check if path exists
if os.path.exists(lastools_bin) == False:
    gp.AddMessage("Cannot find .\\lastools\\bin at " + lastools_bin)
    sys.exit(1)
else:
    gp.AddMessage("Found " + lastools_bin + " ...")

### create the full path to the executable
exe_path = lastools_bin + "\\" + exename

### check if executable exists
if os.path.exists(exe_path + ".exe") == False:
    gp.AddMessage("Cannot find " + exename + ".exe at " + exe_path)
    sys.exit(1)
else:
    gp.AddMessage("Found " + exe_path + " ...")

### create command string
command = ['"' + exe_path + '"']

### maybe use '-verbose' option
if sys.argv[argc - 1] == "true":
    command.append("-v")

### counting up the arguments
c = 1

### add input LiDAR
wildcards = sys.argv[c + 1].split()
for wildcard in wildcards:
    command.append("-i")
    command.append('"' + sys.argv[c] + "\\" + wildcard + '"')
c = c + 2

### maybe we should merge all files into one
if sys.argv[c] == "true":
    command.append("-merged")
c = c + 1

### maybe use a user-defined step size
if sys.argv[c] != "20":
    command.append("-step")
    command.append(sys.argv[c].replace(",", "."))
c = c + 1

### maybe use a user-defined height cutoff
if sys.argv[c].replace(",", ".") != "1.37":
    command.append("-height_cutoff")
    command.append(sys.argv[c].replace(",", "."))
c = c + 1

### maybe there are products requested
products = sys.argv[c].split(";")
for product in products:
    if product[0] == "'":
        subproducts = product[1:-1].split(" ")
        command.append("-" + subproducts[0])
        for subproduct in subproducts[1:]:
            command.append(subproduct)
    else:
        command.append("-" + product)
c = c + 1

### maybe there are count raster requested
counts = sys.argv[c].split()
if len(counts) > 1:
    command.append("-c")
    for count in counts:
        command.append(count.replace(",", "."))
c = c + 1

### maybe there are density raster requested
densities = sys.argv[c].split()
if len(densities) > 1:
    command.append("-d")
    for density in densities:
        command.append(density.replace(",", "."))
c = c + 1

### should we use the bounding box
if sys.argv[c] == "true":
    command.append("-use_bb")
c = c + 1

### should we use the original bounding box
if sys.argv[c] == "true":
    command.append("-use_orig_bb")
c = c + 1

### should we use the tile bounding box
if sys.argv[c] == "true":
    command.append("-use_tile_bb")
c = c + 1

### maybe an output format was selected
if sys.argv[c] != "#":
    command.append("-o" + sys.argv[c])
c = c + 1

### maybe an output file name was selected
if sys.argv[c] != "#":
    command.append("-o")
    command.append('"' + sys.argv[c] + '"')
c = c + 1

### maybe an output directory was selected
if sys.argv[c] != "#":
    command.append("-odir")
    command.append('"' + sys.argv[c] + '"')
c = c + 1

### maybe an output appendix was selected
if sys.argv[c] != "#":
    command.append("-odix")
    command.append('"' + sys.argv[c] + '"')
c = c + 1

### maybe we should run on multiple cores
if sys.argv[c] != "1":
    command.append("-cores")
    command.append(sys.argv[c])
c = c + 1

### maybe there are additional command-line options
if sys.argv[c] != "#":
    additional_options = sys.argv[c].split()
    for option in additional_options:
        command.append(option)

### report command string
gp.AddMessage("LAStools command line:")
command_length = len(command)
command_string = str(command[0])
command[0] = command[0].strip('"')
for i in range(1, command_length):
    command_string = command_string + " " + str(command[i])
    command[i] = command[i].strip('"')
gp.AddMessage(command_string)

### run command
returncode, output = check_output(command, False)

### report output
if is64:
    if returncode == 0:
        gp.AddMessage(str(output))
    elif returncode == 1:
        gp.AddWarning(str(output))
    else:
        gp.AddError(str(output))
else:
    ### win 32: returncode not relieable - parse output
    if str(output).count("WARNING:") > 0:
        gp.AddWarning(str(output))
        returncode = 1
    elif str(output).count("ERROR:") > 0:
        gp.AddError(str(output))
        returncode = 3
    else:
        gp.AddMessage(str(output))

### return code
if returncode == 0:
    gp.AddMessage("Success. " + exename + " done.")
elif returncode == 1:
    gp.AddWarning("Warnings. " + exename + " done.")
else:
    gp.AddError("Error. " + exename + " failed.")
sys.exit(returncode)
