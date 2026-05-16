#
# las2demPro.py
#
# (c) 2025 rapidlasso GmbH - http://rapidlasso.com
#     fast tools to catch reality
#
# uses las2dem.exe to raster a folder of LiDAR files
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
exename = "las2dem"

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

### maybe use a user-defined step size
if sys.argv[c] != "1":
    command.append("-step")
    command.append(sys.argv[c].replace(",", "."))
c = c + 1

### maybe use a user-defined kill
if sys.argv[c] != "100":
    command.append("-kill")
    command.append(sys.argv[c].replace(",", "."))
c = c + 1

### what should we raster
if sys.argv[c] == "slope":
    command.append("-slope")
elif sys.argv[c] == "intensity":
    command.append("-intensity")
elif sys.argv[c] == "rgb":
    command.append("-rgb")
c = c + 1

### what should we output
if sys.argv[c] == "hillshade":
    command.append("-hillshade")
elif sys.argv[c] == "gray ramp":
    command.append("-gray")
elif sys.argv[c] == "false colors":
    command.append("-false")

### do we have special lighting for hillshade
if sys.argv[c] == "hillshade":
    if (sys.argv[c + 1] != "north east") or (sys.argv[c + 2] != "1 pm"):
        command.append("-light")
        if sys.argv[c + 1] == "north":
            command.append("0")
            command.append("1.41421")
        elif sys.argv[c + 1] == "south":
            command.append("0")
            command.append("-1.41421")
        elif sys.argv[c + 1] == "east":
            command.append("1.41421")
            command.append("0")
        elif sys.argv[c + 1] == "west":
            command.append("-1.41421")
            command.append("0")
        elif sys.argv[c + 1] == "north east":
            command.append("1")
            command.append("1")
        elif sys.argv[c + 1] == "south east":
            command.append("1")
            command.append("-1")
        elif sys.argv[c + 1] == "north west":
            command.append("-1")
            command.append("1")
        else:  ### if sys.argv[c+1] == "south west"
            command.append("-1")
            command.append("-1")
        if sys.argv[c + 2] == "noon":
            command.append("100")
        elif sys.argv[c + 2] == "1 pm":
            command.append("2")
        elif sys.argv[c + 2] == "3 pm":
            command.append("1")
        elif sys.argv[c + 2] == "6 pm":
            command.append("0.5")
        else:  ### if sys.argv[c+2] == "9 pm"
            command.append("0.1")

### do we have a min max value for colors
if (sys.argv[c] == "gray ramp") or (sys.argv[c] == "false colors"):
    if (sys.argv[c + 3] != "#") and (sys.argv[c + 4] != "#"):
        command.append("-set_min_max")
        command.append(sys.argv[c + 3].replace(",", "."))
        command.append(sys.argv[c + 4].replace(",", "."))
c = c + 5

### what should we triangulate
if sys.argv[c] == "ground points only":
    command.append("-keep_class")
    command.append("2")
    command.append("-extra_pass")
elif sys.argv[c] == "ground and keypoints":
    command.append("-keep_class")
    command.append("2")
    command.append("8")
    command.append("-extra_pass")
elif sys.argv[c] == "ground and buildings":
    command.append("-keep_class")
    command.append("2")
    command.append("6")
    command.append("-extra_pass")
elif sys.argv[c] == "ground and vegetation":
    command.append("-keep_class")
    command.append("2")
    command.append("3")
    command.append("4")
    command.append("5")
    command.append("-extra_pass")
elif sys.argv[c] == "ground and objects":
    command.append("-keep_class")
    command.append("2")
    command.append("3")
    command.append("4")
    command.append("5")
    command.append("6")
    command.append("-extra_pass")
elif sys.argv[c] == "last return only":
    command.append("-last_only")
    command.append("-extra_pass")
elif sys.argv[c] == "first return only":
    command.append("-first_only")
    command.append("-extra_pass")
c = c + 1

### should we use the tile bounding box
if sys.argv[c] == "true":
    command.append("-use_tile_bb")
c = c + 1

### do we have lakes
if sys.argv[c] != "#":
    command.append("-lakes")
    command.append('"' + sys.argv[c] + '"')
c = c + 1

### do we have creeks
if sys.argv[c] != "#":
    command.append("-creeks")
    command.append('"' + sys.argv[c] + '"')
c = c + 1

### maybe an output format was selected
if sys.argv[c] != "#":
    command.append("-o" + sys.argv[c])
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
