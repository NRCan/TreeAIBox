Esri Optimized LAS I/O Library and API
Build Version: 1.0.0.1
Version: 1.0


Esri Optimized LAS (zLAS) I/O Library and API for Windows 32-bit and Windows 64-bit README
------------------------------------------------------------------------------------------

PURPOSE:

  This is a C++ runtime library for reading and writing Esri Optimized LAS (*.zlas) format files.


PRIMARY CAPABILITIES:
  - Convert zLAS files into LAS files. LAS is an ASPRS industry standard format for lidar data.
  - Convert LAS files into zLAS files.
  - Read zLAS into memory buffers as LAS formatted data (e.g., header record, point data records).
  - Read zLAS into structs for easy interpretation of LAS information.

SUPPORTED PLATFORMS:
  Windows XP SP3 or higher (32-bit and 64-bit)

SOFTWARE REQUIREMENTS:
  Visual Studio 2008 or higher

CONTENTS:
  EzLasLib\Include\EzLasAPIs.h
  EzLasLib\x32\EzLasLib_32.dll
  EzLasLib\x32\EzLasLib_32.lib
  EzLasLib\x64\EzLasLib.dll
  EzLasLib\x64\EzLasLib.lib
  EzLasLib\Examples.cpp
  EzLasLib\README.txt (this file)

HELP:
  All methods are commented with help in the EzLasAPIs.h file.
  An Examples.cpp containing instructional source code is included in the top level EzLasLib folder.

LICENSING:

Copyright 2015 Esri

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
