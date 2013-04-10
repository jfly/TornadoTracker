#!/usr/bin/env python

import sys
import subprocess
gittools = __import__('git-tools')
gittools.cdIntoScriptDir()

extraCmds = subprocess.list2cmdline(sys.argv[1:])
if extraCmds:
   extraCmds = ' ' + extraCmds

project = gittools.GitSensitiveProject(
     name='tornadotracker',
     compileCommand='',
     runCommand='python WatchTornadoDirectory.py' + extraCmds)
gittools.startGitSensitiveScreen('tornadotracker', [project])
