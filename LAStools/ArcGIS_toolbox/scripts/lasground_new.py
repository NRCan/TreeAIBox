#
# lasground_new.py
#
# (c) 2025 rapidlasso GmbH - http://rapidlasso.com
#     fast tools to catch reality
#
# uses lasground_new.exe to extract bare-earth points of
# a LiDAR file. classifies points into ground (class 2)
# and non-ground points (class 1).
#
# LiDAR input:   LAS/LAZ/BIN/TXT/SHP/BIL/ASC/DTM
# LiDAR output:  LAS/LAZ/BIN/TXT
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
exename = "lasground_new"

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
command.append("-i")
command.append('"' + sys.argv[c] + '"')
c = c + 1

### maybe no airborne LiDAR
if sys.argv[c] != "true":
    command.append("-not_airborne")
c = c + 1

### maybe horizontal feet
if sys.argv[c] == "true":
    command.append("-feet")
c = c + 1

### maybe vertical feet
if sys.argv[c] == "true":
    command.append("-elevation_feet")
c = c + 1

### step - terrain_type
# 1=archeology
# 3=wilderness
# 5=nature
# 10=town
# 25=city
# 50=metro
if sys.argv[c] != "#":
    command.append("-step")
    command.append(sys.argv[c].split("=")[0])
c = c + 1

### substep - granularity
# 3=extra_coarse
# 4=coarse
# 6=fine
# 7=extra_fine
# 8=ultra_fine
# 9=hyper_fine
if sys.argv[c] != "#":
    command.append("-sub")
    command.append(sys.argv[c].split("=")[0])
c = c + 1

if sys.argv[c] != "0":
    command.append("-spike")
    command.append(sys.argv[c])
c = c + 1

### maybe we should compute the heights (e.g. for subsequent lasclassify)
if sys.argv[c] == "true":
    command.append("-compute_height")
c = c + 1

### maybe we should height-normalize the LiDAR (e.g. for subsequent canopy creation)
if sys.argv[c] == "true":
    command.append("-replace_z")
c = c + 1

if sys.argv[c] == "true":
    command.append("-store_in_user_data")
c = c + 1

### maybe an output format was selected
if sys.argv[c] != "#":
    if sys.argv[c] == "las":
        command.append("-olas")
    elif sys.argv[c] == "laz":
        command.append("-olaz")
    elif sys.argv[c] == "bin":
        command.append("-obin")
    elif sys.argv[c] == "xyzc":
        command.append("-otxt")
        command.append("-oparse")
        command.append("xyzc")
    elif sys.argv[c] == "xyzci":
        command.append("-otxt")
        command.append("-oparse")
        command.append("xyzci")
    elif sys.argv[c] == "txyzc":
        command.append("-otxt")
        command.append("-oparse")
        command.append("txyzc")
    elif sys.argv[c] == "txyzci":
        command.append("-otxt")
        command.append("-oparse")
        command.append("txyzci")
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
