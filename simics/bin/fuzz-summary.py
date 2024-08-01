#!/usr/bin/env python3
#
# given a an AFL session named by target, provide a summary of
# queue files and unique hits files (post playAFL).
#
# TBD add items from afl fuzzer_stats file, e.g., stability
#
import sys
import os
import glob
import json
import argparse
import subprocess
from datetime import datetime

try:
    import ConfigParser
except:
    import configparser as ConfigParser
resim_dir = os.getenv('RESIM_DIR')

sys.path.append(os.path.join(resim_dir, 'simics', 'monitorCore'))
import aflPath

def getRecentDelta(flist):
    recent = None
    for f in flist:
        dt = os.path.getmtime(f)
        if recent is None or dt > recent:
            recent = dt
    now = datetime.now()
    now_ts = datetime.timestamp(now)
    delta = now_ts - recent
    #print('delta is %d' % delta)
    #dt = datetime.fromtimestamp(recent)
    #print('recent is %s' % str(recent))
    #print(dt.strftime("%m/%d/%Y, %H:%M:%S"))
    return delta

def main():
    afldir = os.getenv('AFL_DIR')
    parser = argparse.ArgumentParser(prog='fuzz-summary.py', description='Show fuzzing summary')
    parser.add_argument('target', action='store', help='The target workspace name.')
    args = parser.parse_args()
    
    unique_files = aflPath.getTargetQueue(args.target)
    queue_files = aflPath.getTargetQueue(args.target, get_all=True)
    crash_files = aflPath.getTargetCrashes(args.target)
    hang_files = aflPath.getTargetHangs(args.target)
    print('AFL found %d queue files (execution paths), some may be duplicates.' % len(queue_files))
    print('RESim sees %d unique execution paths.' % len(unique_files))
    print('\t %d crashes' % len(crash_files))
    print('\t %d hangs' % len(hang_files))
    delta_queue = getRecentDelta(queue_files)
    print('Most recent queue file %d seconds ago' % delta_queue)
if __name__ == '__main__':
    sys.exit(main())
